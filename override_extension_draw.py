# This is a separate library that overrides the extension_draw_item method from Blender extensions list display.
# the original code is in the bl_extension_ui.py file in the Blender source code.
# The override library can be placed in multiple addons, and the override should happen only once.
# The override is done by replacing the original method with the new one, and backing up the original method.
# The original method is then called from the new method, with the same arguments, but with the new code added.
"""
# original code looks like this in Blender 4.2:
def extension_draw_item(
    layout,
    *,
    pkg_id,  # `str`
    item_local,  # `PkgManifest_Normalized | None`
    item_remote,  # `PkgManifest_Normalized | None`
    is_enabled,  # `bool`
    is_outdated,  # `bool`
    show,  # `bool`.
    mark,  # `bool | None`.
    # General vars.
    repo_index,  # `int`
    repo_item,  # `RepoItem`
    operation_in_progress,  # `bool`
    extensions_warnings,  # `dict[str, list[str]]`
):
    item = item_local or item_remote
    is_installed = item_local is not None
    has_remote = repo_item.remote_url != ""

    if item_remote is not None:
        pkg_block = item_remote.block
    else:
        pkg_block = None

    if is_enabled:
        item_warnings = extensions_warnings.get(pkg_repo_module_prefix(repo_item) + pkg_id, [])
    else:
        item_warnings = []

    # Left align so the operator text isn't centered.
    colsub = layout.column()
    row = colsub.row(align=True)

    if show:
        props = row.operator("extensions.package_show_clear", text="", icon='DOWNARROW_HLT', emboss=False)
    else:
        props = row.operator("extensions.package_show_set", text="", icon='RIGHTARROW', emboss=False)
    props.pkg_id = pkg_id
    props.repo_index = repo_index
    del props

    if mark is not None:
        if mark:
            props = row.operator("extensions.package_mark_clear", text="", icon='RADIOBUT_ON', emboss=False)
        else:
            props = row.operator("extensions.package_mark_set", text="", icon='RADIOBUT_OFF', emboss=False)
        props.pkg_id = pkg_id
        props.repo_index = repo_index
        del props

    sub = row.row()
    sub.active = is_enabled
    # Without checking `is_enabled` here, there is no way for the user to know if an extension
    # is enabled or not, which is useful to show - when they may be considering removing/updating
    # extensions based on them being used or not.
    if pkg_block or item_warnings:
        sub.label(text=item.name, icon='ERROR', translate=False)
    else:
        sub.label(text=item.name, translate=False)

    del sub

    # Add a top-level row so `row_right` can have a grayed out button/label
    # without graying out the menu item since# that is functional.
    row_right_toplevel = row.row(align=True)
    if operation_in_progress:
        row_right_toplevel.enabled = False
    row_right_toplevel.alignment = 'RIGHT'
    row_right = row_right_toplevel.row()
    row_right.alignment = 'RIGHT'

    if has_remote and (item_remote is not None):
        if pkg_block is not None:
            row_right.label(text="Blocked   ")
        elif is_installed:
            if is_outdated:
                props = row_right.operator("extensions.package_install", text="Update")
                props.repo_index = repo_index
                props.pkg_id = pkg_id
                props.enable_on_install = is_enabled
                del props
        else:
            props = row_right.operator("extensions.package_install", text="Install")
            props.repo_index = repo_index
            props.pkg_id = pkg_id
            del props
    else:
        # Right space for alignment with the button.
        if has_remote and (item_remote is None):
            # There is a local item with no remote
            row_right.label(text="Orphan   ")

        row_right.active = False

    row_right = row_right_toplevel.row(align=True)
    row_right.alignment = 'RIGHT'
    row_right.separator()

    # NOTE: Keep space between any buttons and this menu to prevent stray clicks accidentally running install.
    # The separator is around together with the align to give some space while keeping the button and the menu
    # still close-by. Used `extension_path` so the menu can access "this" extension.
    row_right.context_string_set("extension_path", "{:s}.{:s}".format(repo_item.module, pkg_id))
    row_right.menu("USERPREF_MT_extensions_item", text="", icon='DOWNARROW_HLT')
    del row_right
    del row_right_toplevel

    if show:
        import os
        from bpy.app.translations import pgettext_iface as iface_

        col = layout.column()

        row = col.row()
        row.active = is_enabled

        # The full tagline may be multiple lines (not yet supported by Blender's UI).
        row.label(text=" {:s}.".format(item.tagline), translate=False)

        col.separator(type='LINE')
        del col

        col_info = layout.column()
        col_info.active = is_enabled
        split = col_info.split(factor=0.15)
        col_a = split.column()
        col_b = split.column()
        col_a.alignment = "RIGHT"

        if pkg_block is not None:
            col_a.label(text="Blocked")
            col_b.label(text=pkg_block.reason, translate=False)

        if item_warnings:
            col_a.label(text="Warning")
            col_b.label(text=item_warnings[0])
            if len(item_warnings) > 1:
                for value in item_warnings[1:]:
                    col_a.label(text="")
                    col_b.label(text=value)
                # pylint: disable-next=undefined-loop-variable
                del value

        if value := (item_remote or item_local).website:
            col_a.label(text="Website")
            col_b.split(factor=0.5).operator(
                "wm.url_open",
                text=domain_extract_from_url(value),
                icon='URL',
            ).url = value
        del value

        if item.type == "add-on":
            col_a.label(text="Permissions")
            # WARNING: while this is documented to be a dict, old packages may contain a list of strings.
            # As it happens dictionary keys & list values both iterate over string,
            # however we will want to show the dictionary values eventually.
            if value := item.permissions:
                col_b.label(text=", ".join([iface_(x).title() for x in value]), translate=False)
            else:
                col_b.label(text="No permissions specified")
            del value

        col_a.label(text="Maintainer")
        col_b.label(text=item.maintainer, translate=False)

        col_a.label(text="Version")
        if is_outdated:
            col_b.label(
                text=iface_("{:s} ({:s} available)").format(item.version, item_remote.version),
                translate=False,
            )
        else:
            col_b.label(text=item.version, translate=False)

        if has_remote and (item_remote is not None):
            col_a.label(text="Size")
            col_b.label(text=size_as_fmt_string(item_remote.archive_size), translate=False)

        col_a.label(text="License")
        col_b.label(text=item.license, translate=False)

        col_a.label(text="Repository")
        col_b.label(text=repo_item.name, translate=False)

        if is_installed:
            col_a.label(text="Path")
            col_b.label(text=os.path.join(repo_item.directory, pkg_id), translate=False)
            """

import json
import os
import bpy
import bl_pkg.bl_extension_ui as exui
from . import icons
from bl_ui.space_userpref import (
    USERPREF_PT_addons,
    USERPREF_PT_extensions,
    USERPREF_MT_extensions_active_repo,
)
from bpy.props import EnumProperty

EXTENSIONS_API_URL = "https://staging.blenderkit.com/api/v1/extensions/"


def extension_draw_item_blenderkit(
    layout,
    *,
    pkg_id,  # `str`
    item_local,  # `PkgManifest_Normalized | None`
    item_remote,  # `PkgManifest_Normalized | None`
    is_enabled,  # `bool`
    is_outdated,  # `bool`
    show,  # `bool`.
    mark,  # `bool | None`.
    # General vars.
    repo_index,  # `int`
    repo_item,  # `RepoItem`
    operation_in_progress,  # `bool`
    extensions_warnings,  # `dict[str, list[str]]`
):
    # filter by verification state, only for blenderkit repository
    if repo_item.remote_url == EXTENSIONS_API_URL:
        # ensure cache is loaded
        ensure_repo_cache()
        # get the cache
        bk_ext_cache = bpy.context.window_manager["blenderkit_extensions_repo_cache"]
        bk_cache_pkg = bk_ext_cache.get(pkg_id[:32], None)
        # get the filter setting
        search_verification_status = (
            bpy.context.window_manager.blenderkit_extension_validation_settings.search_verification_status
        )
        # filter blenderkit packages based on verification status

        if search_verification_status != "ALL":
            if (
                bk_cache_pkg is not None
                and not bk_cache_pkg.get("verification_status")
                == search_verification_status.lower()
            ):
                return False

    exui.extension_draw_item_original(
        layout,
        pkg_id=pkg_id,
        item_local=item_local,
        item_remote=item_remote,
        is_enabled=is_enabled,
        is_outdated=is_outdated,
        show=show,
        mark=mark,
        repo_index=repo_index,
        repo_item=repo_item,
        operation_in_progress=operation_in_progress,
        extensions_warnings=extensions_warnings,
    )
    # Folded state:
    if not repo_item.remote_url == EXTENSIONS_API_URL:
        return True

    if bk_cache_pkg is None:
        return True

    row = layout.row()

    if not show:
        # blenderkit logo icon
        pcoll = icons.icon_collections["main"]
        icon_value = pcoll["logo"].icon_id
        row.label(text="This is folded state", icon_value=icon_value)
        # verification status
        row.label(text="Verification status: " + bk_cache_pkg["verification_status"])

    if show:
        layout.separator()
        row.label(text="Unfoldeeed state")
    # link to
    # print(dir(item_local))

    # which of it could contain original data from api?
    # archive_size, archive_url, block, license, maintainer, name, permissions, tagline, tags, type, version, website, wheels
    return True


def override_draw_function():
    print("overriding extension draw function")
    if hasattr(exui, "extension_draw_item_original"):
        print("already overridden")
        return False
    exui.extension_draw_item_original = exui.extension_draw_item
    exui.extension_draw_item = extension_draw_item_blenderkit
    return True


def get_repository_by_url(url: str):
    """Get the repository by its remote URL, from registered blenderkit Extension repositories."""
    for r in bpy.context.preferences.extensions.repos:
        if r.remote_url == url:
            return r
    return None


def ensure_repo_cache():
    # this reads the .json file blender stores in \extensions\www_blenderkit_com\.blender_ext
    # and parses it to a dict from json, we can use it then for drawing purposes and have the extra data BlenderKit api provides

    # return if cache already exists
    if "blenderkit_extensions_repo_cache" in bpy.context.window_manager:
        return

    blenderkit_repository = get_repository_by_url(EXTENSIONS_API_URL)
    if blenderkit_repository is None:
        return
    # get the path to the cache file which is in repository directory under /.blender_ext/index.json
    cache_file = os.path.join(
        blenderkit_repository.directory, ".blender_ext", "index.json"
    )
    if not os.path.exists(cache_file):
        return
    with open(cache_file, "r") as f:
        data = f.read()
    # the data needs to be written to a location in memory where it's possibly accessible from all addons but doesn't get saved in blender file
    # we can use window manager for that
    wm = bpy.context.window_manager
    data = json.loads(data)
    # store the data as a dict with keys being the package names
    wm["blenderkit_extensions_repo_cache"] = {}
    for pkg in data["data"]:
        #
        print(pkg)
        wm["blenderkit_extensions_repo_cache"][pkg["id"][:32]] = pkg


def ensure_repo_order():
    """Ensure that the blenderkit repository is the first one in the list of repositories.
    We need to cache and delete all other online repositories, and create them new after blenderkit, with all props the same.
    """
    # get the blenderkit repository
    blenderkit_repository = get_repository_by_url(EXTENSIONS_API_URL)
    if blenderkit_repository is None:
        return

    # get all repositories
    all_repos = bpy.context.preferences.extensions.repos
    # get all online repositories except blenderkit
    online_repos = []  # need to convert repos to dicts
    remove_online_repos = []
    for r in all_repos:
        if r.remote_url != EXTENSIONS_API_URL and r.remote_url != "":

            repo_dict = {
                "name": r.name,
                "module": r.module,
                "use_remote_url": r.use_remote_url,
                "remote_url": r.remote_url,
                "use_sync_on_startup": r.use_sync_on_startup,
                "use_cache": r.use_cache,
                "use_access_token": r.use_access_token,
                "access_token": r.access_token,
                "use_custom_directory": r.use_custom_directory,
                "custom_directory": r.custom_directory,
                "enabled": r.enabled,
            }
            online_repos.append(repo_dict)
            remove_online_repos.append(r)

    # remove all online repositories except blenderkit
    for r in remove_online_repos:
        all_repos.remove(r)

    # add all other repositories back
    for r in online_repos:
        # complete list of properties of a repository:
        #'access_token', 'custom_directory', 'directory', 'enabled', 'module', 'name', 'remote_url', 'rna_type', 'source', 'use_access_token', 'use_cache', 'use_custom_directory', 'use_remote_url', 'use_sync_on_startup'

        new_repo = all_repos.new()
        new_repo.name = r["name"]
        new_repo.module = r["module"]
        new_repo.use_remote_url = r["use_remote_url"]
        new_repo.remote_url = r["remote_url"]
        new_repo.use_sync_on_startup = r["use_sync_on_startup"]
        new_repo.use_cache = r["use_cache"]
        new_repo.use_access_token = r["use_access_token"]
        new_repo.access_token = r["access_token"]
        new_repo.use_custom_directory = r["use_custom_directory"]
        new_repo.custom_directory = r["custom_directory"]
        new_repo.enabled = r["enabled"]


def ensure_repository(api_key: str = ""):
    """Ensure that the blenderkit extensions repository is correctly added in Blender's preferences.
    If the repository is not present, it is added. If the repository is present, but the API key is not set, it is set.
    """

    blenderkit_repository = get_repository_by_url(EXTENSIONS_API_URL)

    if blenderkit_repository is None:

        blenderkit_repository = bpy.context.preferences.extensions.repos.new()
        blenderkit_repository.name = "www.blenderkit.com"
        blenderkit_repository.module = "www_blenderkit_com"
        blenderkit_repository.use_remote_url = True
        blenderkit_repository.remote_url = EXTENSIONS_API_URL
        blenderkit_repository.use_sync_on_startup = True

    if api_key != "":
        blenderkit_repository.use_access_token = True
        blenderkit_repository.access_token = api_key
    else:
        # let's try to import blenderkit preferences and get the api key
        # try:
        user_preferences = bpy.context.preferences.addons[__package__].preferences
        api_key = user_preferences.api_key
        if api_key != "":
            blenderkit_repository.use_access_token = True
            blenderkit_repository.access_token = api_key
        # except:
        # pass
    ensure_repo_order()
    ensure_repo_cache()


# small separate preferences prop group on the window manager to store some validator settings
class BlenderKiExtensionValidationSettings(bpy.types.PropertyGroup):
    search_verification_status: EnumProperty(
        name="Verification status",
        description="Search by verification status",
        items=(
            ("ALL", "All", "All"),
            ("UPLOADING", "Uploading", "Uploading"),
            ("UPLOADED", "Uploaded", "Uploaded"),
            ("READY", "Ready for V.", "Ready for validation (deprecated since 2.8)"),
            ("VALIDATED", "Validated", "Validated"),
            ("ON_HOLD", "On Hold", "On Hold"),
            ("REJECTED", "Rejected", "Rejected"),
            ("DELETED", "Deleted", "Deleted"),
        ),
        default="ALL",
    )


def draw_validation_addons(panel, context):
    layout = panel.layout
    row = layout.row()
    # verification  enum as row of buttons
    row.prop(
        context.window_manager.blenderkit_extension_validation_settings,
        "search_verification_status",
        expand=True,
    )


def register():
    bpy.utils.register_class(BlenderKiExtensionValidationSettings)
    bpy.types.WindowManager.blenderkit_extension_validation_settings = (
        bpy.props.PointerProperty(type=BlenderKiExtensionValidationSettings)
    )
    ensure_repository()
    override_draw_function()
    USERPREF_PT_extensions.prepend(draw_validation_addons)
