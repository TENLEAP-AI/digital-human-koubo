/* Grid maze router core. Built by route.py with: gcc -O2 -shared -fPIC route_core.c -o route_core.so -lm
 *
 * Coordinates are grid cells. Per routing layer there are three maps:
 *   owner  : 0 = free, n > 0 = only net n may put a track centre here, -1 = nobody may
 *            (copper of every net is painted grown by clearance + half a default track)
 *   copper : net id where real copper (a pad core, a track centre line, a via centre) is
 *   comp   : connected-component id of that copper (union-find below)
 * viablock marks cells where no via centre may go (other holes, pads, board edge).
 */
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static int W, H, L;
static int32_t *owner, *copper, *comp;
static int32_t *owner_fixed;   /* like owner, but only things that are never ripped up (pads, edge, frozen nets) */
static uint8_t *viablock, *viablock_fixed;
static int paint_fixed = 0;    /* when set, painting also goes into the *_fixed maps */
static int32_t *dist, *parent;
static uint32_t *stamp;
static int8_t *pdir;
static uint32_t epoch = 0;
static uint32_t *vstamp;       /* per (x, y): epoch at which viaval was computed */
static uint8_t *viaval;
static int wx0, wy0, wx1, wy1; /* search window */
static int16_t *cnt;           /* negotiated routing: how many halos of movable tracks cover a cell */
static int16_t *vcnt;          /* per (x, y): how many movable vias are too close for another hole */
static uint16_t *hist;         /* per cell: cost that builds up where nets keep getting in each other's way */
static int ldir[16];           /* per layer: 0 = any direction, 1 = mostly horizontal, 2 = mostly vertical */

static int *uf;
static uint8_t *plane_ok;
static int uf_n = 1, uf_cap = 0;

typedef struct { int32_t cost; int32_t s; } HNode;
static HNode *heap;
static int heap_n = 0, heap_cap = 0;

int rt_init(int w, int h, int l) {
    W = w; H = h; L = l;
    size_t n = (size_t)W * H * L;
    owner = calloc(n, sizeof(int32_t));
    owner_fixed = calloc(n, sizeof(int32_t));
    viablock_fixed = calloc((size_t)W * H, 1);
    copper = calloc(n, sizeof(int32_t));
    comp = calloc(n, sizeof(int32_t));
    dist = malloc(n * sizeof(int32_t));
    parent = malloc(n * sizeof(int32_t));
    stamp = calloc(n, sizeof(uint32_t));
    pdir = malloc(n);
    viablock = calloc((size_t)W * H, 1);
    vstamp = calloc((size_t)W * H, sizeof(uint32_t));
    viaval = malloc((size_t)W * H);
    cnt = calloc(n, sizeof(int16_t));
    vcnt = calloc((size_t)W * H, sizeof(int16_t));
    hist = calloc(n, sizeof(uint16_t));
    uf_cap = 4096;
    uf = malloc(uf_cap * sizeof(int));
    plane_ok = calloc(uf_cap, 1);
    uf_n = 1;
    return owner && copper && comp && dist && parent && stamp && pdir && viablock && uf && plane_ok && cnt && vcnt && hist;
}

void rt_clear(void) {
    size_t n = (size_t)W * H * L;
    memset(owner, 0, n * sizeof(int32_t));
    memset(owner_fixed, 0, n * sizeof(int32_t));
    memset(viablock_fixed, 0, (size_t)W * H);
    memset(copper, 0, n * sizeof(int32_t));
    memset(comp, 0, n * sizeof(int32_t));
    memset(viablock, 0, (size_t)W * H);
    memset(cnt, 0, n * sizeof(int16_t));
    memset(vcnt, 0, (size_t)W * H * sizeof(int16_t));
    uf_n = 1;
}

void rt_clear_hist(void) { memset(hist, 0, (size_t)W * H * L * sizeof(uint16_t)); }

int rt_new_comp(int plane) {
    if (uf_n >= uf_cap) {
        uf_cap *= 2;
        uf = realloc(uf, uf_cap * sizeof(int));
        plane_ok = realloc(plane_ok, uf_cap);
    }
    uf[uf_n] = uf_n;
    plane_ok[uf_n] = (uint8_t)plane;
    return uf_n++;
}

int rt_find(int a) {
    while (uf[a] != a) { uf[a] = uf[uf[a]]; a = uf[a]; }
    return a;
}

void rt_unite(int a, int b) {
    a = rt_find(a); b = rt_find(b);
    if (a != b) { uf[b] = a; plane_ok[a] |= plane_ok[b]; }
}

void rt_set_dirs(const int *dirs) { for (int l = 0; l < L && l < 16; l++) ldir[l] = dirs[l]; }
void rt_set_plane(int a) { plane_ok[rt_find(a)] = 1; }
void rt_set_fixed(int on) { paint_fixed = on; }
int rt_plane(int a) { return plane_ok[rt_find(a)]; }

/* distance from point p to segment a-b */
static double seg_dist(double px, double py, double ax, double ay, double bx, double by) {
    double vx = bx - ax, vy = by - ay, wx = px - ax, wy = py - ay;
    double len2 = vx * vx + vy * vy, t = len2 > 0 ? (wx * vx + wy * vy) / len2 : 0;
    if (t < 0) t = 0; else if (t > 1) t = 1;
    double dx = px - (ax + t * vx), dy = py - (ay + t * vy);
    return sqrt(dx * dx + dy * dy);
}

static inline void own(int32_t *map, size_t idx, int net) {
    int32_t v = map[idx];
    if (net < 0) map[idx] = -1;
    else if (v == 0) map[idx] = net;
    else if (v != net) map[idx] = -1;
}

static inline void apply(int mode, size_t idx, int net, int cid) {
    if (mode == 0) {                       /* owner */
        own(owner, idx, net);
        if (paint_fixed) own(owner_fixed, idx, net);
    } else {                               /* copper: touching copper of the same net becomes one component */
        if (copper[idx] == net && comp[idx] && comp[idx] != cid) rt_unite(cid, comp[idx]);
        copper[idx] = net;
        comp[idx] = cid;
    }
}

/* axis-aligned rectangle grown by r (rounded corners) */
void rt_paint_rect(int layer, double x0, double y0, double x1, double y1, double r, int net, int mode, int cid) {
    int ix0 = (int)floor(x0 - r), ix1 = (int)ceil(x1 + r), iy0 = (int)floor(y0 - r), iy1 = (int)ceil(y1 + r);
    if (ix0 < 0) ix0 = 0; if (iy0 < 0) iy0 = 0; if (ix1 >= W) ix1 = W - 1; if (iy1 >= H) iy1 = H - 1;
    for (int iy = iy0; iy <= iy1; iy++)
        for (int ix = ix0; ix <= ix1; ix++) {
            double dx = ix < x0 ? x0 - ix : (ix > x1 ? ix - x1 : 0);
            double dy = iy < y0 ? y0 - iy : (iy > y1 ? iy - y1 : 0);
            if (dx * dx + dy * dy <= r * r + 1e-9)
                apply(mode, ((size_t)layer * H + iy) * W + ix, net, cid);
        }
}

/* segment grown by r (a capsule); a disc when both ends coincide */
void rt_paint_seg(int layer, double x0, double y0, double x1, double y1, double r, int net, int mode, int cid) {
    double lx = x0 < x1 ? x0 : x1, hx = x0 < x1 ? x1 : x0, ly = y0 < y1 ? y0 : y1, hy = y0 < y1 ? y1 : y0;
    int ix0 = (int)floor(lx - r), ix1 = (int)ceil(hx + r), iy0 = (int)floor(ly - r), iy1 = (int)ceil(hy + r);
    if (ix0 < 0) ix0 = 0; if (iy0 < 0) iy0 = 0; if (ix1 >= W) ix1 = W - 1; if (iy1 >= H) iy1 = H - 1;
    for (int iy = iy0; iy <= iy1; iy++)
        for (int ix = ix0; ix <= ix1; ix++)
            if (seg_dist(ix, iy, x0, y0, x1, y1) <= r + 1e-9)
                apply(mode, ((size_t)layer * H + iy) * W + ix, net, cid);
}

void rt_viablock_rect(double x0, double y0, double x1, double y1, double r) {
    int ix0 = (int)floor(x0 - r), ix1 = (int)ceil(x1 + r), iy0 = (int)floor(y0 - r), iy1 = (int)ceil(y1 + r);
    if (ix0 < 0) ix0 = 0; if (iy0 < 0) iy0 = 0; if (ix1 >= W) ix1 = W - 1; if (iy1 >= H) iy1 = H - 1;
    for (int iy = iy0; iy <= iy1; iy++)
        for (int ix = ix0; ix <= ix1; ix++) {
            double dx = ix < x0 ? x0 - ix : (ix > x1 ? ix - x1 : 0);
            double dy = iy < y0 ? y0 - iy : (iy > y1 ? iy - y1 : 0);
            if (dx * dx + dy * dy <= r * r + 1e-9) {
                viablock[(size_t)iy * W + ix] = 1;
                if (paint_fixed) viablock_fixed[(size_t)iy * W + ix] = 1;
            }
        }
}

/* mask: W*H bytes, 0 = outside the usable board area */
void rt_block_mask(const uint8_t *mask, int vias_only) {
    for (int iy = 0; iy < H; iy++)
        for (int ix = 0; ix < W; ix++) {
            if (mask[(size_t)iy * W + ix]) continue;
            viablock[(size_t)iy * W + ix] = 1;
            viablock_fixed[(size_t)iy * W + ix] = 1;
            if (!vias_only)
                for (int l = 0; l < L; l++) {
                    owner[((size_t)l * H + iy) * W + ix] = -1;
                    owner_fixed[((size_t)l * H + iy) * W + ix] = -1;
                }
        }
}

int rt_owner_at(int layer, int x, int y) { return owner[((size_t)layer * H + y) * W + x]; }
int rt_copper_at(int layer, int x, int y) { return copper[((size_t)layer * H + y) * W + x]; }
int rt_comp_at(int layer, int x, int y) { return comp[((size_t)layer * H + y) * W + x]; }

static void heap_push(int32_t cost, int32_t s) {
    if (heap_n >= heap_cap) {
        heap_cap = heap_cap ? heap_cap * 2 : 1 << 16;
        heap = realloc(heap, heap_cap * sizeof(HNode));
    }
    int i = heap_n++;
    while (i > 0) {
        int p = (i - 1) / 2;
        if (heap[p].cost <= cost) break;
        heap[i] = heap[p];
        i = p;
    }
    heap[i].cost = cost; heap[i].s = s;
}

static HNode heap_pop(void) {
    HNode top = heap[0], last = heap[--heap_n];
    int i = 0;
    for (;;) {
        int c = 2 * i + 1;
        if (c >= heap_n) break;
        if (c + 1 < heap_n && heap[c + 1].cost < heap[c].cost) c++;
        if (heap[c].cost >= last.cost) break;
        heap[i] = heap[c];
        i = c;
    }
    heap[i] = last;
    return top;
}

static int rip_mode = 0;        /* 1: other nets' rippable tracks do not block, they only cost extra */

static inline int usable(int net, int l, int x, int y, int np, const int *probe) {
    const int32_t *map = rip_mode ? owner_fixed : owner;
    for (int i = 0; i < np; i++) {
        int xx = x + probe[2 * i], yy = y + probe[2 * i + 1];
        if (xx < 0 || yy < 0 || xx >= W || yy >= H) return 0;
        int32_t v = map[((size_t)l * H + yy) * W + xx];
        if (v != 0 && v != net) return 0;
    }
    return 1;
}

static inline int via_ok(int net, int x, int y, int nvp, const int *vprobe) {
    if ((rip_mode ? viablock_fixed : viablock)[(size_t)y * W + x]) return 0;
    for (int l = 0; l < L; l++)
        if (!usable(net, l, x, y, nvp, vprobe)) return 0;
    return 1;
}

int rt_via_ok(int net, int x, int y, int nvp, const int *vprobe) { rip_mode = 0; return via_ok(net, x, y, nvp, vprobe); }
int rt_usable(int net, int l, int x, int y, int np, const int *probe) { rip_mode = 0; return usable(net, l, x, y, np, probe); }

static const int DX[8] = {1, 1, 0, -1, -1, -1, 0, 1};
static const int DY[8] = {0, 1, 1, 1, 0, -1, -1, -1};

/* Shortest path from component `src` of `net` to other copper of the same net.
 * lcost[l]   : cost multiplier of layer l, 0 = layer not allowed for this net
 * probe      : cell offsets that must all be free for a track centre (one {0,0} for a thin track)
 * vprobe     : same for a via centre
 * plane_mode : the net has a plane; stop at copper that already reaches the plane, or at the
 *              first spot where a via can go (kind 1)
 * out        : states (layer*H + y)*W + x from the end back to the start
 * returns the number of states, 0 when no path exists; *kind = 0 joined copper, 1 new via  */
static inline int via_cached(int net, int x, int y, int nvp, const int *vprobe) {
    size_t i = (size_t)y * W + x;
    if (vstamp[i] != epoch) { vstamp[i] = epoch; viaval[i] = (uint8_t)via_ok(net, x, y, nvp, vprobe); }
    return viaval[i];
}

void rt_window(int x0, int y0, int x1, int y1) {
    wx0 = x0 < 0 ? 0 : x0; wy0 = y0 < 0 ? 0 : y0;
    wx1 = x1 >= W ? W - 1 : x1; wy1 = y1 >= H ? H - 1 : y1;
}

int rt_route(int net, int src, const int *lcost, int viacost, int np, const int *probe, int nvp,
             const int *vprobe, int plane_mode, int rip_pen, int32_t *out, int outcap, int *kind) {
    int root = rt_find(src);
    int maxcost = 0;
    rip_mode = rip_pen > 0;
    epoch++;
    heap_n = 0;
    for (int l = 0; l < L; l++) {
        if (!lcost[l]) continue;
        for (int y = wy0; y <= wy1; y++) {
            size_t base = ((size_t)l * H + y) * W;
            for (int x = wx0; x <= wx1; x++) {
                size_t s = base + x;
                if (copper[s] == net && rt_find(comp[s]) == root) {
                    stamp[s] = epoch; dist[s] = 0; parent[s] = -1; pdir[s] = -1;
                    heap_push(0, (int32_t)s);
                }
            }
        }
    }
    int32_t end = -1;
    *kind = 0;
    while (heap_n > 0) {
        HNode h = heap_pop();
        int32_t s = h.s;
        if (h.cost > dist[s]) continue;
        if (maxcost > 0 && h.cost > maxcost) break;
        int l = s / (W * H), rem = s % (W * H), y = rem / W, x = rem % W;
        if (copper[s] == net) {
            int r = rt_find(comp[s]);
            if (r != root && (!plane_mode || plane_ok[r])) { end = s; *kind = 0; break; }
        }
        if (plane_mode && h.cost > 0 && copper[s] != net && via_cached(net, x, y, nvp, vprobe)) {
            end = s; *kind = 1; break;
        }
        for (int d = 0; d < 8; d++) {
            int nx = x + DX[d], ny = y + DY[d];
            if (nx < wx0 || ny < wy0 || nx > wx1 || ny > wy1) continue;
            if (!usable(net, l, nx, ny, np, probe)) continue;
            int32_t ns = (int32_t)(((size_t)l * H + ny) * W + nx);
            int step = (d & 1) ? 14 : 10;
            if ((ldir[l] == 1 && DY[d]) || (ldir[l] == 2 && DX[d])) step *= 3;   /* against the layer's direction */
            int32_t c = h.cost + step * lcost[l];
            if (rip_mode) {
                int32_t v = owner[ns];
                if (v != 0 && v != net) c += rip_pen;
            }
            if (pdir[s] >= 0 && pdir[s] != d) {
                int turn = abs(pdir[s] - d);
                if (turn > 4) turn = 8 - turn;
                c += turn == 1 ? 6 : 30;
            }
            if (stamp[ns] != epoch || c < dist[ns]) {
                stamp[ns] = epoch; dist[ns] = c; parent[ns] = s; pdir[ns] = (int8_t)d;
                heap_push(c, ns);
            }
        }
        if (viacost > 0 && via_cached(net, x, y, nvp, vprobe))
            for (int l2 = 0; l2 < L; l2++) {
                if (l2 == l || !lcost[l2]) continue;
                if (!usable(net, l2, x, y, np, probe)) continue;
                int32_t ns = (int32_t)(((size_t)l2 * H + y) * W + x);
                int32_t c = h.cost + viacost;
                if (rip_mode && viablock[(size_t)y * W + x]) c += 20 * rip_pen;
                if (stamp[ns] != epoch || c < dist[ns]) {
                    stamp[ns] = epoch; dist[ns] = c; parent[ns] = s; pdir[ns] = -1;
                    heap_push(c, ns);
                }
            }
    }
    if (end < 0) return 0;
    int cnt = 0;
    for (int32_t s = end; s >= 0 && cnt < outcap; s = parent[s]) out[cnt++] = s;
    return cnt;
}


/* ---- negotiated routing ---------------------------------------------------------------------
 * Fixed copper (pads, board edge, keep-outs, nets that are not up for negotiation) blocks as before,
 * through owner_fixed and viablock_fixed. The tracks and vias of the nets being negotiated do not
 * block each other: every cell they cover (grown by the clearance, as in the owner map) is counted
 * in cnt, and a track through such a cell pays for it. The price goes up from round to round, and
 * cells where nets keep colliding collect a history cost, until no net is in another's way. */

void rt_cnt_seg(int layer, double x0, double y0, double x1, double y1, double r, int delta) {
    double lx = x0 < x1 ? x0 : x1, hx = x0 < x1 ? x1 : x0, ly = y0 < y1 ? y0 : y1, hy = y0 < y1 ? y1 : y0;
    int ix0 = (int)floor(lx - r), ix1 = (int)ceil(hx + r), iy0 = (int)floor(ly - r), iy1 = (int)ceil(hy + r);
    if (ix0 < 0) ix0 = 0; if (iy0 < 0) iy0 = 0; if (ix1 >= W) ix1 = W - 1; if (iy1 >= H) iy1 = H - 1;
    for (int iy = iy0; iy <= iy1; iy++)
        for (int ix = ix0; ix <= ix1; ix++)
            if (seg_dist(ix, iy, x0, y0, x1, y1) <= r + 1e-9)
                cnt[((size_t)layer * H + iy) * W + ix] += (int16_t)delta;
}

/* a via: its pad on every layer (radius r), and the area where no other hole may be (radius rb) */
void rt_cnt_via(double x, double y, double r, double rb, int delta) {
    for (int l = 0; l < L; l++) rt_cnt_seg(l, x, y, x, y, r, delta);
    int ix0 = (int)floor(x - rb), ix1 = (int)ceil(x + rb), iy0 = (int)floor(y - rb), iy1 = (int)ceil(y + rb);
    if (ix0 < 0) ix0 = 0; if (iy0 < 0) iy0 = 0; if (ix1 >= W) ix1 = W - 1; if (iy1 >= H) iy1 = H - 1;
    for (int iy = iy0; iy <= iy1; iy++)
        for (int ix = ix0; ix <= ix1; ix++)
            if ((ix - x) * (ix - x) + (iy - y) * (iy - y) <= rb * rb + 1e-9)
                vcnt[(size_t)iy * W + ix] += (int16_t)delta;
}

/* forget the copper of `net` along a segment (its pads are painted again by the caller) */
void rt_erase_seg(int layer, double x0, double y0, double x1, double y1, double r, int net) {
    double lx = x0 < x1 ? x0 : x1, hx = x0 < x1 ? x1 : x0, ly = y0 < y1 ? y0 : y1, hy = y0 < y1 ? y1 : y0;
    int ix0 = (int)floor(lx - r), ix1 = (int)ceil(hx + r), iy0 = (int)floor(ly - r), iy1 = (int)ceil(hy + r);
    if (ix0 < 0) ix0 = 0; if (iy0 < 0) iy0 = 0; if (ix1 >= W) ix1 = W - 1; if (iy1 >= H) iy1 = H - 1;
    for (int iy = iy0; iy <= iy1; iy++)
        for (int ix = ix0; ix <= ix1; ix++) {
            size_t idx = ((size_t)layer * H + iy) * W + ix;
            if (copper[idx] == net && seg_dist(ix, iy, x0, y0, x1, y1) <= r + 1e-9) { copper[idx] = 0; comp[idx] = 0; }
        }
}

/* the same for a rectangle grown by r: a pad's copper, before the pad is painted again as a component of its own */
void rt_erase_rect(int layer, double x0, double y0, double x1, double y1, double r, int net) {
    int ix0 = (int)floor(x0 - r), ix1 = (int)ceil(x1 + r), iy0 = (int)floor(y0 - r), iy1 = (int)ceil(y1 + r);
    if (ix0 < 0) ix0 = 0; if (iy0 < 0) iy0 = 0; if (ix1 >= W) ix1 = W - 1; if (iy1 >= H) iy1 = H - 1;
    for (int iy = iy0; iy <= iy1; iy++)
        for (int ix = ix0; ix <= ix1; ix++) {
            size_t idx = ((size_t)layer * H + iy) * W + ix;
            if (copper[idx] == net) { copper[idx] = 0; comp[idx] = 0; }
        }
}

static inline void hist_add(size_t idx, int add) {
    uint32_t h = (uint32_t)hist[idx] + (uint32_t)add;
    hist[idx] = (uint16_t)(h > 60000 ? 60000 : h);
}

/* cells within r of a segment that lie in another net's way; `add` goes onto their history cost.
 * Call it while the net's own copper is not counted in cnt. */
int rt_conflict_seg(int layer, double x0, double y0, double x1, double y1, double r, int add) {
    double lx = x0 < x1 ? x0 : x1, hx = x0 < x1 ? x1 : x0, ly = y0 < y1 ? y0 : y1, hy = y0 < y1 ? y1 : y0;
    int ix0 = (int)floor(lx - r), ix1 = (int)ceil(hx + r), iy0 = (int)floor(ly - r), iy1 = (int)ceil(hy + r);
    if (ix0 < 0) ix0 = 0; if (iy0 < 0) iy0 = 0; if (ix1 >= W) ix1 = W - 1; if (iy1 >= H) iy1 = H - 1;
    int n = 0;
    for (int iy = iy0; iy <= iy1; iy++)
        for (int ix = ix0; ix <= ix1; ix++) {
            size_t idx = ((size_t)layer * H + iy) * W + ix;
            if (cnt[idx] > 0 && seg_dist(ix, iy, x0, y0, x1, y1) <= r + 1e-9) {
                n++;
                if (add) hist_add(idx, add);
            }
        }
    return n;
}

int rt_conflict_via(double x, double y, double r, int add) {
    int n = 0;
    for (int l = 0; l < L; l++) n += rt_conflict_seg(l, x, y, x, y, r, add);
    int ix = (int)floor(x + 0.5), iy = (int)floor(y + 0.5);
    if (ix >= 0 && iy >= 0 && ix < W && iy < H && vcnt[(size_t)iy * W + ix] > 0) {
        n++;
        if (add) for (int l = 0; l < L; l++) hist_add(((size_t)l * H + iy) * W + ix, add);
    }
    return n;
}

/* -1: fixed copper in the way; otherwise the largest number of movable halos over the probe cells */
static inline int soft(int net, int l, int x, int y, int np, const int *probe) {
    int g = 0;
    for (int i = 0; i < np; i++) {
        int xx = x + probe[2 * i], yy = y + probe[2 * i + 1];
        if (xx < 0 || yy < 0 || xx >= W || yy >= H) return -1;
        size_t idx = ((size_t)l * H + yy) * W + xx;
        int32_t v = owner_fixed[idx];
        if (v != 0 && v != net) return -1;
        if (cnt[idx] > g) g = cnt[idx];
    }
    return g;
}

static inline int via_soft(int net, int x, int y, int nvp, const int *vprobe) {
    size_t i = (size_t)y * W + x;
    if (vstamp[i] != epoch) {
        int g = -1;
        if (!viablock_fixed[i]) {
            g = vcnt[i] > 0 ? vcnt[i] : 0;
            for (int l = 0; l < L; l++) {
                int s = soft(net, l, x, y, nvp, vprobe);
                if (s < 0) { g = -1; break; }
                if (s > g) g = s;
            }
        }
        vstamp[i] = epoch;
        viaval[i] = g < 0 ? 255 : (uint8_t)(g > 250 ? 250 : g);
    }
    return viaval[i] == 255 ? -1 : viaval[i];
}

/* like rt_route, but movable copper of other nets costs instead of blocking.
 * pf: price of sharing, in eighths (8 = a shared cell costs twice as much per halo over it)
 * conf: receives how much of the path lies in another net's way (cells, and 20 for each such via) */
int rt_route_neg(int net, int src, const int *lcost, int viacost, int np, const int *probe, int nvp,
                 const int *vprobe, int pf, int32_t *out, int outcap, int *conf) {
    int root = rt_find(src);
    epoch++;
    heap_n = 0;
    for (int l = 0; l < L; l++) {
        if (!lcost[l]) continue;
        for (int y = wy0; y <= wy1; y++) {
            size_t base = ((size_t)l * H + y) * W;
            for (int x = wx0; x <= wx1; x++) {
                size_t s = base + x;
                if (copper[s] == net && rt_find(comp[s]) == root) {
                    stamp[s] = epoch; dist[s] = 0; parent[s] = -1; pdir[s] = -1;
                    heap_push(0, (int32_t)s);
                }
            }
        }
    }
    int32_t end = -1;
    while (heap_n > 0) {
        HNode h = heap_pop();
        int32_t s = h.s;
        if (h.cost > dist[s]) continue;
        int l = s / (W * H), rem = s % (W * H), y = rem / W, x = rem % W;
        if (copper[s] == net && rt_find(comp[s]) != root) { end = s; break; }
        for (int d = 0; d < 8; d++) {
            int nx = x + DX[d], ny = y + DY[d];
            if (nx < wx0 || ny < wy0 || nx > wx1 || ny > wy1) continue;
            int g = soft(net, l, nx, ny, np, probe);
            if (g < 0) continue;
            int32_t ns = (int32_t)(((size_t)l * H + ny) * W + nx);
            int step = (d & 1) ? 14 : 10;
            if ((ldir[l] == 1 && DY[d]) || (ldir[l] == 2 && DX[d])) step *= 3;
            int32_t base = step * lcost[l];
            int32_t c = h.cost + base + hist[ns];
            if (g) c += (int32_t)(((int64_t)base * pf * g) >> 3);
            if (pdir[s] >= 0 && pdir[s] != d) {
                int turn = abs(pdir[s] - d);
                if (turn > 4) turn = 8 - turn;
                c += turn == 1 ? 6 : 30;
            }
            if (stamp[ns] != epoch || c < dist[ns]) {
                stamp[ns] = epoch; dist[ns] = c; parent[ns] = s; pdir[ns] = (int8_t)d;
                heap_push(c, ns);
            }
        }
        if (viacost > 0) {
            int gv = via_soft(net, x, y, nvp, vprobe);
            if (gv >= 0)
                for (int l2 = 0; l2 < L; l2++) {
                    if (l2 == l || !lcost[l2]) continue;
                    if (soft(net, l2, x, y, np, probe) < 0) continue;
                    int32_t ns = (int32_t)(((size_t)l2 * H + y) * W + x);
                    int32_t c = h.cost + viacost + hist[ns];
                    if (gv) c += (int32_t)(((int64_t)viacost * pf * gv) >> 3);
                    if (stamp[ns] != epoch || c < dist[ns]) {
                        stamp[ns] = epoch; dist[ns] = c; parent[ns] = s; pdir[ns] = -1;
                        heap_push(c, ns);
                    }
                }
        }
    }
    *conf = 0;
    if (end < 0) return 0;
    int n = 0;
    for (int32_t s = end; s >= 0 && n < outcap; s = parent[s]) {
        int l = s / (W * H), rem = s % (W * H), y = rem / W, x = rem % W;
        if (soft(net, l, x, y, np, probe) > 0) (*conf)++;
        if (parent[s] >= 0 && parent[s] / (W * H) != l && via_soft(net, x, y, nvp, vprobe) > 0) *conf += 20;
        out[n++] = s;
    }
    return n;
}
