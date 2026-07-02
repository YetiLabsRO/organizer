import { TestBed } from '@angular/core/testing';

import { ItemCacheService } from './item-cache.service';

describe('ItemCacheService', () => {
  let service: ItemCacheService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ItemCacheService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
