const AREA_COLORS = {
  red: { background: '#FDE2E0', color: '#9B2C2C' },
  blue: { background: '#DCEBFF', color: '#1E4F91' },
  green: { background: '#DDF5E7', color: '#176B3A' },
  purple: { background: '#EEE3FF', color: '#653A96' },
  orange: { background: '#FFE9D2', color: '#9A4E12' },
  yellow: { background: '#FFF5C9', color: '#7B5C00' },
  brown: { background: '#F0E1D6', color: '#74452B' },
};

export function areaColor(areaOrKey) {
  const key = typeof areaOrKey === 'string' ? areaOrKey : areaOrKey?.color_key;
  return AREA_COLORS[key] || AREA_COLORS.blue;
}
