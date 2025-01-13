# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

import logging

from . import client_tasks, global_vars


bk_logger = logging.getLogger(__name__)


### COMMENTS
def handle_get_comments_task(task: client_tasks.Task):
    """Handle incomming task which downloads comments on asset."""
    if task.status == "error":
        return bk_logger.warning(f"failed to get comments: {task.message}")
    if task.status == "finished":
        comments = task.result["results"]
        store_comments_local(task.data["asset_id"], comments)
        return


def handle_create_comment_task(task: client_tasks.Task):
    """Handle incoming task for creating a new comment."""
    if task.status == "finished":
        return bk_logger.debug(f"Creating comment finished - {task.message}")
    if task.status == "error":
        return bk_logger.warning(f"Creating comment failed - {task.message}")


def handle_feedback_comment_task(task: client_tasks.Task):
    """Handle incomming task for update of feedback on comment."""
    if task.status == "finished":  # action not needed
        return bk_logger.debug(f"Comment feedback finished - {task.message}")
    if task.status == "error":
        return bk_logger.warning(f"Comment feedback failed - {task.message}")


def handle_mark_comment_private_task(task: client_tasks.Task):
    """Handle incomming task for marking the comment as private/public."""
    if task.status == "finished":  # action not needed
        return bk_logger.debug(f"Marking comment visibility finished - {task.message}")
    if task.status == "error":
        return bk_logger.warning(f"Marking comment visibility failed - {task.message}")


def store_comments_local(asset_id, comments):
    global_vars.DATA["asset comments"][asset_id] = comments


def get_comments_local(asset_id):
    return global_vars.DATA["asset comments"].get(asset_id)


### NOTIFICATIONS
def handle_notifications_task(task: client_tasks.Task):
    """Handle incomming task with notifications data."""
    if task.status == "finished":
        global_vars.DATA["bkit notifications"] = task.result
        return
    if task.status == "error":
        return bk_logger.warning(f"Notifications fetching failed: {task.message}")


def check_notifications_read():
    """Check if all notifications were already read, and remove them if so."""
    notifications = global_vars.DATA.get("bkit notifications")
    if notifications is None:
        return True
    if notifications.get("count") == 0:
        return True

    for notification in notifications["results"]:
        if notification["unread"] == 1:
            return False

    global_vars.DATA["bkit notifications"] = None
    return True
