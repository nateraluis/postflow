from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import utils
from .models import GlassAccount, ManualPostTask


@login_required
def manual_queue(request):
    tasks = (
        ManualPostTask.objects.filter(
            scheduled_post__user=request.user, status__in=["waiting", "ready"]
        )
        .select_related("scheduled_post")
        .prefetch_related("scheduled_post__images")
        .order_by("ready_at", "created_at")
    )
    done_tasks = (
        ManualPostTask.objects.filter(
            scheduled_post__user=request.user, status__in=["posted", "skipped"]
        )
        .select_related("scheduled_post")
        .prefetch_related("scheduled_post__images")
        .order_by("-completed_at")[:10]
    )
    accounts = request.user.glass_accounts.all()

    return render(
        request,
        "glass/queue.html",
        {
            "tasks": tasks,
            "done_tasks": done_tasks,
            "accounts": accounts,
            "active_page": "glass",
        },
    )


@login_required
@require_POST
def add_account(request):
    username = request.POST.get("username", "").strip().lstrip("@")
    if not username:
        messages.error(request, "Enter a Glass username.")
        return redirect("glass:queue")

    _, created = GlassAccount.objects.get_or_create(user=request.user, username=username)
    if created:
        messages.success(request, f"Added Glass account @{username}.")
    else:
        messages.info(request, f"Glass account @{username} is already connected.")
    return redirect("glass:queue")


@login_required
@require_POST
def delete_account(request, pk):
    account = get_object_or_404(GlassAccount, pk=pk, user=request.user)
    username = account.username
    account.delete()
    messages.success(request, f"Removed Glass account @{username}.")
    return redirect("glass:queue")


@login_required
@require_POST
def mark_posted(request, pk):
    task = get_object_or_404(
        ManualPostTask, pk=pk, scheduled_post__user=request.user
    )
    utils.complete_task(task, posted_url=request.POST.get("posted_url", ""))
    messages.success(request, "Marked as posted.")
    return redirect("glass:queue")


@login_required
@require_POST
def skip_task(request, pk):
    task = get_object_or_404(
        ManualPostTask, pk=pk, scheduled_post__user=request.user
    )
    utils.skip_task(task)
    messages.info(request, "Skipped.")
    return redirect("glass:queue")
