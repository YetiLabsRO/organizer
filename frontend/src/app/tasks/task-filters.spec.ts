import { TaskFilters } from './task-filters';

describe('TaskFilters', () => {
  it('should create an instance', () => {
    expect(new TaskFilters()).toBeTruthy();
  });

  it('omits the project when the list is not scoped to one', () => {
    expect(new TaskFilters().getQueryString()).not.toContain('project=');
  });

  it('carries the project id into the query string', () => {
    const filters = new TaskFilters();
    filters.project = 7;

    expect(filters.getFilteredURL('/api/task/')).toContain('project=7');
  });

  it('carries the project id into the router query params', () => {
    const filters = new TaskFilters();
    filters.project = 7;

    expect(filters.getQueryParams()['project']).toBe('7');
  });
});
