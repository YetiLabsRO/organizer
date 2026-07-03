/**
 * Pick black or white text for readability on a hex background colour.
 * (WCAG-style luminance contrast — shared by the tag pipe and autocomplete UI.)
 */
export function tagTextColor(bgColor: string, lightColor = '#FFFFFF', darkColor = '#000000'): string {
  const luminance = (hexColor: string): number => {
    if (hexColor === '#FFFFFF') return 1;
    if (hexColor === '#000000') return 0;
    const color = hexColor.charAt(0) === '#' ? hexColor.substring(1, 7) : hexColor;
    const r = parseInt(color.substring(0, 2), 16);
    const g = parseInt(color.substring(2, 4), 16);
    const b = parseInt(color.substring(4, 6), 16);
    const channels = [r / 255, g / 255, b / 255].map((c) =>
      c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
    );
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  };

  const L = luminance(bgColor);
  const L1 = luminance(lightColor);
  const L2 = luminance(darkColor);
  return L > Math.sqrt((L1 + 0.05) * (L2 + 0.05)) - 0.05 ? darkColor : lightColor;
}
