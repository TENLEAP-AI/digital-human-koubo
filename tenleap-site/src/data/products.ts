// 产品数据：名字、价格、卖点、规格全是占位（TODO），换成 Tenleap 真实产品。
// art 决定产品插画样式：watch | band | ring。有实拍图后改成 image 字段即可。
export type Product = {
  slug: string;
  name: string;
  category: string;
  price: string;
  status: 'available' | 'preorder' | 'coming';
  short: string;
  art: 'watch' | 'band' | 'ring';
  hue: string;
  highlights: { title: string; text: string }[];
  specs: [string, string][];
};

export const products: Product[] = [
  {
    slug: 'leap-watch-s1',
    name: 'Leap Watch S1',
    category: 'AI Smartwatch',
    price: '$149',
    status: 'preorder',
    short: 'A 1.43" AMOLED smartwatch with an on-wrist AI coach that reads your sleep, heart and training load.',
    art: 'watch',
    hue: '#C6F432',
    highlights: [
      { title: 'AI daily brief', text: 'Wake up to one clear recommendation built from sleep, HRV and yesterday’s activity.' },
      { title: '14-day battery', text: 'Typical use on a single charge, with always-on display options.' },
      { title: 'Custom watch faces', text: 'Design and sync your own faces from the companion app.' },
    ],
    specs: [
      ['Display', '1.43" AMOLED, 466 × 466'],
      ['Sensors', 'Heart rate, SpO₂, accelerometer, gyroscope'],
      ['Battery', 'Up to 14 days typical'],
      ['Water resistance', '5 ATM'],
      ['Connectivity', 'Bluetooth 5.3'],
      ['Compatibility', 'iOS 14+ / Android 8+'],
    ],
  },
  {
    slug: 'leap-band-2',
    name: 'Leap Band 2',
    category: 'Health Band',
    price: '$59',
    status: 'available',
    short: 'Featherlight 24/7 health tracking with sleep staging, stress and recovery scores.',
    art: 'band',
    hue: '#5EE6D0',
    highlights: [
      { title: 'Sleep you can read', text: 'Stages, interruptions and a plain-language score every morning.' },
      { title: '21 g', text: 'Light enough to forget you are wearing it — until it is useful.' },
      { title: '20-day battery', text: 'Charge twice a month in typical use.' },
    ],
    specs: [
      ['Display', '1.1" AMOLED'],
      ['Weight', '21 g with strap'],
      ['Battery', 'Up to 20 days typical'],
      ['Water resistance', '5 ATM'],
      ['Connectivity', 'Bluetooth 5.3'],
      ['Compatibility', 'iOS 14+ / Android 8+'],
    ],
  },
  {
    slug: 'leap-ring',
    name: 'Leap Ring',
    category: 'Smart Ring',
    price: '$199',
    status: 'coming',
    short: 'A titanium smart ring that tracks sleep, heart rate, HRV and skin temperature — no screen, no distractions.',
    art: 'ring',
    hue: '#FF8A3D',
    highlights: [
      { title: 'Sleep, measured at the finger', text: 'Finger-based sensing for steadier overnight heart rate, HRV and temperature trends.' },
      { title: '7-day battery', text: 'A week of 24/7 tracking, with a compact charging dock.' },
      { title: 'Nothing to look at', text: 'No screen and no buzzing — insights wait for you in the app.' },
    ],
    specs: [
      ['Material', 'Titanium shell, hypoallergenic inner coating'],
      ['Sensors', 'Heart rate, SpO₂, skin temperature, accelerometer'],
      ['Battery', 'Up to 7 days typical'],
      ['Water resistance', '10 ATM'],
      ['Sizes', 'US 6–13 (free sizing kit before you buy)'],
      ['Compatibility', 'iOS 14+ / Android 8+'],
    ],
  },
];

export const statusLabel: Record<Product['status'], string> = {
  available: 'Available now',
  preorder: 'Pre-order',
  coming: 'Coming soon',
};
