import {Tag} from '../tags/tag';
import {query} from '@angular/animations';
import {formatDate} from '@angular/common';

export class TaskFilters {
  [k: string]: any;

  completed: boolean | null;
  contains: string | null;
  completed_date: Date | null;
  tags: Tag[] | null;
  for_today: boolean | null;

  constructor(completed: boolean | null = null,
              contains: string | null = null,
              completed_date: Date | null = null,
              tags: Tag[] | null = null,
              forToday: boolean | null = null) {
    this.completed = completed;
    this.contains = contains;
    this.completed_date = completed_date;
    this.tags = tags;
    this.for_today = forToday;
  }

  getQueryString(): string {
    let queryItems: string[] = [];
    let filterList: string[] = ["completed", "contains", "for_today"]

    filterList.forEach((item => {
      if (this[item] !== null) {
        queryItems.push(`${item}=${this[item]}`)
      }
    }))

    if (!!this.tags) {
      this.tags.forEach((tag: Tag) => {
        queryItems.push(`tags=${tag.slug}`);
      })
    }

    if (this.completed_date) {
      queryItems.push(`completed_date=${formatDate(this.completed_date, "yyyy-MM-dd", 'en-US')}`)
    }

    return queryItems.join("&")
  }

  getFilteredURL(url: string): string {
    let queryString = this.getQueryString()
    return queryString ? `${url}?${queryString}` : url
  }
}


