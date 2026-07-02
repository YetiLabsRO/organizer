import { Pipe, PipeTransform } from '@angular/core';
import {Tag} from './tags/tag';

@Pipe({
  name: 'reverseLuminanceColor'
})
export class ReverseLuminanceColorPipe implements PipeTransform {

  transform(value: string, ...args: unknown[]): unknown {
      return this.getReverseLuminanceColor(value);
  }

  // https://stackoverflow.com/questions/3942878/how-to-decide-font-color-in-white-or-black-depending-on-background-color
  getReverseLuminanceColor (bgColor: string, lightColor = '#FFFFFF', darkColor = '#000000'): string {
    const getLuminance = function (hexColor: string) {
      if(hexColor === "#FFFFFF") return 1.;
      if(hexColor === "#000000") return 0.;

      let color = (hexColor.charAt(0) === '#') ? hexColor.substring(1, 7) : hexColor
      let r = parseInt(color.substring(0, 2), 16) // hexToR
      let g = parseInt(color.substring(2, 4), 16) // hexToG
      let b = parseInt(color.substring(4, 6), 16) // hexToB
      let uicolors = [r / 255, g / 255, b / 255]
      let c = uicolors.map(col => col <= 0.03928 ? col / 12.92 : ((col + 0.055) / 1.055) ** 2.4)

      return (0.2126 * c[0]) + (0.7152 * c[1]) + (0.0722 * c[2]);
    }

    let L = getLuminance(bgColor)
    let L1 = getLuminance(lightColor)
    let L2 = getLuminance(darkColor)

    return (L > Math.sqrt((L1 + 0.05) * (L2 + 0.05)) - 0.05) ? darkColor : lightColor;
  }


}
