## ADDED Requirements

### Requirement: Task template definition
The system SHALL let an authenticated user define a task template: a reusable blueprint consisting of
a title (required) and optional description, priority, estimated time, project, and tags. Templates
SHALL be owned by the creating user and SHALL only be visible to and editable by their owner.

#### Scenario: Create a minimal template
- **WHEN** an authenticated user POSTs to `/api/template/` with a title and a recurrence rule
- **THEN** a template is created, owned by that user, with priority defaulting to normal and no tasks
  generated yet

#### Scenario: Templates are owner-scoped
- **WHEN** an authenticated user lists `/api/template/`
- **THEN** only templates owned by that user are returned

### Requirement: Structured recurrence rule
A template SHALL carry a structured recurrence rule: a `frequency` of `daily`, `weekly`, `monthly`,
or `yearly`; a positive integer `interval` (default 1) meaning "every N `frequency` units"; an
optional `day_of_month` (1–31) for monthly/yearly rules; an optional set of `weekdays` (Monday–Sunday)
for weekly rules; an optional `month_of_year` (1–12) for yearly rules; an optional `start_on` date
(defaulting to the template's creation date) and optional `end_on` date. The system SHALL also
reserve an optional `rrule` field for a future iCal recurrence string; when `rrule` is set it SHALL
take precedence over the structured fields.

#### Scenario: Monthly on a fixed day
- **WHEN** a template has `frequency = monthly`, `interval = 1`, `day_of_month = 1`
- **THEN** its occurrences fall on the 1st of every month on or after `start_on`

#### Scenario: Every N weeks on chosen weekdays
- **WHEN** a template has `frequency = weekly`, `interval = 2`, `weekdays = [Monday]`
- **THEN** its occurrences fall on every second Monday on or after `start_on`

#### Scenario: Day-of-month clamps to shorter months
- **WHEN** a template has `frequency = monthly`, `day_of_month = 31`
- **THEN** for a month with fewer than 31 days the occurrence falls on that month's last day

#### Scenario: Occurrences stop after end date
- **WHEN** a template has an `end_on` date and the next computed occurrence would fall after it
- **THEN** no further tasks are generated for that template

### Requirement: Scheduled task generation
The system SHALL provide a generation process that materializes real tasks from active templates. The
process SHALL be idempotent, SHALL be runnable both as a Celery beat periodic task and as a
`generate_recurring_tasks` management command, and re-running it within the same day SHALL NOT create
duplicate tasks. A generated task SHALL copy the template's blueprint (title, description, priority,
estimated time, project, tags), be owned by the template's owner, start with status `idea`, and be
linked back to its template.

#### Scenario: A due occurrence generates a task
- **WHEN** the generation process runs on a day when a template has a newly-due occurrence
- **THEN** exactly one task is created from that template's blueprint, linked to the template

#### Scenario: Re-running the same day is a no-op
- **WHEN** the generation process runs again on the same day for the same template
- **THEN** no additional task is created

#### Scenario: Inactive templates do not generate
- **WHEN** a template is marked inactive (paused)
- **THEN** the generation process creates no tasks from it

### Requirement: Latest-missed-only catch-up
The generation process SHALL create a task only for the single most recent due occurrence of a
template and SHALL skip earlier missed occurrences when it has not run for a period spanning multiple
occurrences.

#### Scenario: Downtime does not produce a backlog
- **WHEN** a daily template had three occurrences pass while the generator was not running, and the
  generator then runs
- **THEN** exactly one task is created for the most recent occurrence, not three

### Requirement: Configurable lead time
A template SHALL have a `lead_time_days` value (default 0). A task for an occurrence SHALL become
eligible for generation when the current date is on or after the occurrence date minus
`lead_time_days`, and the generated task's deadline (`end_date`) SHALL be the occurrence date.

#### Scenario: Task appears ahead of its deadline
- **WHEN** a template with `lead_time_days = 3` has an occurrence due on the 1st
- **THEN** the task is generated on the 29th of the prior month with its deadline set to the 1st

#### Scenario: Zero lead time generates on the due date
- **WHEN** a template with `lead_time_days = 0` has an occurrence due on the 1st
- **THEN** the task is generated on the 1st with its deadline set to the 1st

### Requirement: Skip while previous instance is open
A template SHALL have a `skip_if_previous_open` flag (default false). When the flag is set and the
most recently generated task from that template is not completed, the generation process SHALL NOT
create a new task for that template and SHALL NOT advance the template's last-generated marker, so
generation resumes at the then-current occurrence once the open task is completed.

#### Scenario: Open previous instance blocks generation
- **WHEN** `skip_if_previous_open` is true and the last generated task is still incomplete on a day a
  new occurrence is due
- **THEN** no new task is created

#### Scenario: Completing the previous instance resumes generation
- **WHEN** the previously open task is marked completed and the generation process next runs with a
  due occurrence
- **THEN** a new task is created for the current most recent occurrence

### Requirement: Template management API
The system SHALL expose an authenticated, owner-scoped `/api/template/` endpoint supporting create,
retrieve, list, update, and delete of templates, plus a `run` action that generates the template's
currently-due task immediately. The serialized representation SHALL include a human-readable schedule
summary and the next occurrence date.

#### Scenario: Run a template on demand
- **WHEN** an authenticated user POSTs to `/api/template/{id}/run/`
- **THEN** the template's currently-due task is generated immediately and returned

#### Scenario: Serialized template reports its schedule
- **WHEN** an authenticated user retrieves a template
- **THEN** the response includes a human-readable recurrence summary and the next occurrence date

### Requirement: Scheduling infrastructure
The system SHALL run task generation on a recurring schedule using Celery with a Redis broker and
Celery beat. The beat schedule SHALL invoke the generation task at least daily at a configurable hour.
The REST API SHALL continue to function when the broker or workers are unavailable; only automatic
generation is suspended until they recover.

#### Scenario: Beat triggers daily generation
- **WHEN** Celery beat and a worker are running
- **THEN** the generation task runs on its configured daily schedule without manual intervention

#### Scenario: API unaffected when the broker is down
- **WHEN** the Redis broker is unavailable
- **THEN** the REST API continues to serve requests and generation resumes once the broker recovers
