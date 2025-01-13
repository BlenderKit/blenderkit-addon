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

import base64
import hashlib
import logging
import random
import secrets
import string
import time
from urllib.parse import quote as urlquote
from webbrowser import open_new_tab

import bpy
from bpy.props import BoolProperty

from . import client_lib, client_tasks, datas, global_vars, reports, tasks_queue, utils


CLIENT_ID = "IdFRwa3SGA8eMpzhRVFMg5Ts8sPK93xBjif93x0F"
REFRESH_RESERVE = 60 * 60 * 24 * 3  # 3 days
active_authenticator = None
bk_logger = logging.getLogger(__name__)


def handle_login_task(task: client_tasks.Task):
    """Handles incoming task of type Login. Writes tokens if it finished successfully, logouts the user on error."""
    if task.status == "finished":
        tasks_queue.add_task(
            (
                write_tokens,
                (
                    task.result["access_token"],
                    task.result["refresh_token"],
                    task.result,
                ),
            )
        )
    elif task.status == "error":
        logout()
        reports.add_report(task.message, 5, "ERROR")


def handle_token_refresh_task(task: client_tasks.Task):
    """Handle incoming task of type token_refresh. If the new token is meant for the current user, calls handle_login_task.
    Otherwise it ignores the incoming task.
    """
    preferences = bpy.context.preferences.addons[__package__].preferences  # type: ignore
    if task.data.get("old_api_key") != preferences.api_key:  # type: ignore
        bk_logger.info("Refreshed token is not meant for current user. Ignoring.")
        return

    if task.status == "finished":
        reports.add_report(task.message, 5, "INFO")
        tasks_queue.add_task(
            (
                write_tokens,
                (
                    task.result["access_token"],
                    task.result["refresh_token"],
                    task.result,
                ),
            )
        )
    elif task.status == "error":
        logout()
        reports.add_report(task.message, 5, "ERROR")


def handle_logout_task(task: client_tasks.Task):
    """Handles incoming task of type oauth2/logout. This could be triggered from another add-on also.
    Shows messages depending on result of tokens revocation.
    Regardless of revocation results, it also cleans login data."""
    if task.status == "finished":
        reports.add_report(task.message, 3, "INFO")
    elif task.status == "error":
        reports.add_report(task.message, 5, "ERROR")

    clean_login_data()


def clean_login_data():
    preferences = bpy.context.preferences.addons[__package__].preferences
    preferences.login_attempt = False
    preferences.api_key_refresh = ""
    preferences.api_key = ""
    preferences.api_key_timeout = 0
    global_vars.BKIT_PROFILE = datas.MineProfile()


def logout() -> None:
    """Logs out user from add-on. Also calls BlenderKit-client to revoke the tokens."""
    bk_logger.info("Logging out.")
    client_lib.oauth2_logout()
    clean_login_data()


def login(signup: bool) -> None:
    """Logs user into the addon.
    Opens a browser with login page. Once user is logged it redirects browser to Client handling access code via URL querry parameter.
    Using the access_code Client then requests api_token and handles the results as a task with status finished/error.
    This is handled by function handle_login_task which saves tokens, or shows error message.
    """
    local_landing_URL = f"http://localhost:{client_lib.get_port()}/consumer/exchange/"
    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe()
    client_lib.send_oauth_verification_data(code_verifier, state)
    authorize_url = f"/o/authorize?client_id={CLIENT_ID}&response_type=code&state={state}&redirect_uri={local_landing_URL}&code_challenge={code_challenge}&code_challenge_method=S256"
    if signup:
        authorize_url = urlquote(authorize_url)
        authorize_url = f"{global_vars.SERVER}/accounts/register/?next={authorize_url}"
    else:
        authorize_url = f"{global_vars.SERVER}{authorize_url}"
    ok = open_new_tab(authorize_url)
    bk_logger.info(f"Login page in browser opened ({ok})")


def generate_pkce_pair() -> tuple[str, str]:
    """Generate PKCE pair - a code verifier and code challange.
    The challange should be sent first to the server, the verifier is used in next steps to verify identity (handles Client).
    """
    rand = random.SystemRandom()
    code_verifier = "".join(rand.choices(string.ascii_letters + string.digits, k=128))

    code_sha_256 = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    b64 = base64.urlsafe_b64encode(code_sha_256)
    code_challenge = b64.decode("utf-8").replace("=", "")
    return code_verifier, code_challenge


def write_tokens(auth_token, refresh_token, oauth_response):
    preferences = bpy.context.preferences.addons[__package__].preferences
    preferences.api_key_timeout = int(time.time() + oauth_response["expires_in"])
    preferences.login_attempt = False
    preferences.api_key_refresh = refresh_token
    preferences.api_key = auth_token  # triggers api_key update function
    # write token also to extensions repository setting
    if bpy.app.version >= (4, 2, 0):
        from . import override_extension_draw

        override_extension_draw.ensure_repository(api_key=auth_token)

    #


def ensure_token_refresh() -> bool:
    """Check if API token needs refresh, call refresh and return True if so.
    Otherwise do nothing and return False.
    """
    preferences = bpy.context.preferences.addons[__package__].preferences  # type: ignore
    if preferences.api_key == "":  # type: ignore
        return False  # not logged in

    if preferences.api_key_refresh == "":  # type: ignore
        # Using manually inserted permanent token
        return False

    if time.time() + REFRESH_RESERVE < preferences.api_key_timeout:  # type: ignore
        # Token is not old
        return False

    # Token is at the end of life, refresh token exists, it is time to refresh
    client_lib.refresh_token(preferences.api_key_refresh, preferences.api_key)  # type: ignore
    return True


class LoginOnline(bpy.types.Operator):
    """Login or register online on BlenderKit webpage"""

    bl_idname = "wm.blenderkit_login"
    bl_label = "BlenderKit login/signup"
    bl_options = {"REGISTER", "UNDO"}

    signup: BoolProperty(  # type: ignore
        name="create a new account",
        description="True for register, otherwise login",
        default=False,
        options={"SKIP_SAVE"},
    )

    message: bpy.props.StringProperty(  # type: ignore
        name="Message",
        description="",
        default="You were logged out from BlenderKit.\n Clicking OK takes you to web login. ",
    )

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        utils.label_multiline(layout, text=self.message, width=300)

    def execute(self, context):
        preferences = bpy.context.preferences.addons[__package__].preferences
        preferences.login_attempt = True
        login(self.signup)
        return {"FINISHED"}

    def invoke(self, context, event):
        wm = bpy.context.window_manager
        preferences = bpy.context.preferences.addons[__package__].preferences
        preferences.api_key_refresh = ""
        preferences.api_key = ""
        return wm.invoke_props_dialog(self)


class Logout(bpy.types.Operator):
    """Logout from BlenderKit immediately"""

    bl_idname = "wm.blenderkit_logout"
    bl_label = "BlenderKit logout"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        logout()
        return {"FINISHED"}


class CancelLoginOnline(bpy.types.Operator):
    """Cancel login attempt"""

    bl_idname = "wm.blenderkit_login_cancel"
    bl_label = "BlenderKit login cancel"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        preferences = bpy.context.preferences.addons[__package__].preferences
        preferences.login_attempt = False
        return {"FINISHED"}


classes = (
    LoginOnline,
    CancelLoginOnline,
    Logout,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)
