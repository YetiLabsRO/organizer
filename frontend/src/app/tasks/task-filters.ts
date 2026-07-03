import {Tag} from '../tags/tag';
import {formatDate} from '@angular/common';

export class TaskFilters {
  [k: string]: any;

  completed: boolean | null;
  contains: string | null;
  completed_date: Date | null;
  tags: Tag[] | null;
  for_today: boolean | null;
  today_view: boolean | null;

  constructor(completed: boolean | null = null,
              contains: string | null = null,
              completed_date: Date | null = null,
              tags: Tag[] | null = null,
              forToday: boolean | null = null,
              todayView: boolean | null = null) {
    this.completed = completed;
    this.contains = contains;
    this.completed_date = completed_date;
    this.tags = tags;
    this.for_today = forToday;
    this.today_view = todayView;
  }

  getQueryString(): string {
    let queryItems: string[] = [];
    let filterList: string[] = ["completed", "contains", "for_today", "today_view"]

    filterList.forEach((item => {
      if (this[item] !== null) {
        queryItems.push(`${item}=${encodeURIComponent(this[item])}`)
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

  /** Angular Router queryParams object (tags become a repeated key) — used to carry filters into
   *  the stats page so it reflects exactly the list's filters and stays bookmarkable. */
  getQueryParams(): { [k: string]: string | string[] } {
    const params: { [k: string]: string | string[] } = {};
    ["completed", "contains", "for_today", "today_view"].forEach((item) => {
      if (this[item] !== null && this[item] !== undefined) {
        params[item] = String(this[item]);
      }
    });
    if (this.tags && this.tags.length) {
      params["tags"] = this.tags.map((tag: Tag) => tag.slug);
    }
    if (this.completed_date) {
      params["completed_date"] = formatDate(this.completed_date, "yyyy-MM-dd", "en-US");
    }
    return params;
  }
}
