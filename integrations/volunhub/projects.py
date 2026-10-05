"""VolunHub projects -> local ``Project``s: auto-create on first sight, merge on request.

Projects come from the ``project_id`` / ``project_slug`` / ``project_name`` inline on each task, not
from VolunHub's project listing: that listing uses a different notion of "mine" (owned or reported)
and misses projects of tasks that are merely *assigned* to the user.
"""

from django.db import transaction

from integrations.volunhub.models import VolunHubProjectLink, VolunHubTaskLink
from tasks.models import Project


def resolve_project(ref, cache=None):
    """The local project for a VolunHub project ``(id, slug, name)``, creating it on first sight.

    Follows VolunHub renames while the project is still the auto-created one. A project the user
    deleted locally stays deleted (the link's ``project`` is null): tasks then import project-less
    rather than the sync resurrecting it.
    """
    if ref is None:
        return None
    external_id, slug, name = ref
    if cache is not None and external_id in cache:
        return cache[external_id]

    link, created = VolunHubProjectLink.objects.get_or_create(
        external_id=external_id, defaults={"external_slug": slug, "external_name": name}
    )
    if created:
        link.project = Project.objects.create(title=name or slug or f"VolunHub #{external_id}")
        link.auto_created = True
        link.save(update_fields=["project", "auto_created"])
    elif (name and name != link.external_name) or (slug and slug != link.external_slug):
        if name and name != link.external_name and link.auto_created and link.project is not None:
            link.project.title = name
            link.project.save(update_fields=["title"])
        link.external_name = name or link.external_name
        link.external_slug = slug or link.external_slug
        link.save(update_fields=["external_name", "external_slug"])

    if cache is not None:
        cache[external_id] = link.project
    return link.project


def links_visible_to(user):
    """Project links the user may see or merge: those referenced by their own task links."""
    referenced = VolunHubTaskLink.objects.filter(user=user, external_project_id__isnull=False).values(
        "external_project_id"
    )
    return VolunHubProjectLink.objects.filter(external_id__in=referenced).select_related("project")


@transaction.atomic
def merge_project(link, target):
    """Point ``link`` at the existing local project ``target``.

    An auto-created project is folded in completely — every task moves, any other link pointing at
    it follows, and the emptied project is deleted. A project the user owned before (from an earlier
    merge) is never emptied: only the tasks this VolunHub project brought in move.
    """
    previous, was_auto_created = link.project, link.auto_created
    link.project = target
    link.auto_created = False
    link.save(update_fields=["project", "auto_created"])

    if previous is None or previous.pk == target.pk:
        return link

    if was_auto_created:
        tasks = previous.tasks.all()
        VolunHubProjectLink.objects.filter(project=previous).update(project=target, auto_created=False)
    else:
        tasks = previous.tasks.filter(volunhub_link__external_project_id=link.external_id)

    # One save() per task so every move reaches open clients over the WebSocket.
    for task in tasks:
        task.project = target
        task.save()

    if was_auto_created and not previous.tasks.exists():
        previous.delete()
    return link
