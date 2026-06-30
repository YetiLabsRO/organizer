import { Injectable } from '@angular/core';
import {Item} from './item';

@Injectable({
  providedIn: 'root'
})

export class ItemCacheService {
  itemCache: { [id: number] : Item} = {};
  static MAX_AGE = 3600;

  constructor() { }

  updateItem(item: any): void {
    if (item.id in this.itemCache) {
      this.itemCache[item.id].data = item;
      this.itemCache[item.id].timestamp = new Date();
    } else {
      this.itemCache[item.id] = {
        "timestamp": new Date(),
        "data": item
      } as Item;
    }

  }

  updateItems(items: any[]): void {
    items.forEach(item => { this.updateItem(item); });
  }

  getItem(id: number): any | void {
    if ((id in this.itemCache) &&
      ((new Date()).valueOf() - this.itemCache[id].timestamp.valueOf() < ItemCacheService.MAX_AGE)) {
      return this.itemCache[id].data;
    }

    return null;
  }
}
