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

import ctypes
import logging
import os
import platform
import random
import time
from webbrowser import open_new_tab

import bpy
from bpy.props import IntProperty, StringProperty
from bpy.types import Context, Menu, Panel, UILayout

from . import (
    addon_updater_ops,
    asset_bar_op,
    autothumb,
    categories,
    client_lib,
    comments_utils,
    datas,
    download,
    global_vars,
    icons,
    paths,
    ratings,
    ratings_utils,
    search,
    ui,
    upload,
    utils,
)


ACCEPTABLE_ENGINES = ("CYCLES", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT")

bk_logger = logging.getLogger(__name__)

last_time_dropdown_active = 0.0


def draw_not_logged_in(source, message="Please Login/Signup to use this feature"):
    title = "You aren't logged in"

    def draw_message(source, context):
        layout = source.layout
        utils.label_multiline(layout, text=message)
        draw_login_buttons(layout)

    bpy.context.window_manager.popup_menu(draw_message, title=title, icon="INFO")


def draw_upload_common(layout, props, asset_type, context):
    asset_type_text = asset_type.lower()
    if asset_type == "MODEL":
        url = paths.BLENDERKIT_MODEL_UPLOAD_INSTRUCTIONS_URL
    if asset_type == "MATERIAL":
        url = paths.BLENDERKIT_MATERIAL_UPLOAD_INSTRUCTIONS_URL
    if asset_type == "BRUSH":
        url = paths.BLENDERKIT_BRUSH_UPLOAD_INSTRUCTIONS_URL
    if asset_type == "SCENE":
        url = paths.BLENDERKIT_SCENE_UPLOAD_INSTRUCTIONS_URL
    if asset_type == "HDR":
        asset_type_text = asset_type
        url = paths.BLENDERKIT_HDR_UPLOAD_INSTRUCTIONS_URL
    if asset_type == "NODEGROUP":
        asset_type_text = asset_type
        url = ""  # paths.BLENDERKIT_NODEGROUP_UPLOAD_INSTRUCTIONS_URL
    op = layout.operator(
        "wm.url_open", text=f"Read {asset_type} upload instructions", icon="QUESTION"
    )
    op.url = url

    row = layout.row(align=True)
    if props.upload_state != "":
        utils.label_multiline(
            layout, text=props.upload_state, width=context.region.width
        )
    if props.uploading:
        op = layout.operator("object.kill_bg_process", text="", icon="CANCEL")
        op.process_source = asset_type
        op.process_type = "UPLOAD"
        layout = layout.column()
        layout.enabled = False
    # if props.upload_state.find('Error') > -1:
    #     layout.label(text = props.upload_state)

    # PRE-RELEASED WARNING
    if props.is_private == "PUBLIC" and bpy.app.version_cycle != "release":
        layout.row()
        utils.label_multiline(
            layout,
            text="Uploading from Alpha, Beta, or Release Candidate versions of Blender is not recommended. Please use a Stable version.",
            icon="ERROR",
            width=210,
        )

    if props.asset_base_id == "":
        optext = "Upload %s" % asset_type.lower()
        op = layout.operator("object.blenderkit_upload", text=optext, icon="EXPORT")
        op.asset_type = asset_type
        op.reupload = False
        # make sure everything gets uploaded.
        op.main_file = True
        op.metadata = True
        op.thumbnail = True

    if props.asset_base_id != "":
        op = layout.operator(
            "wm.blenderkit_url", text="Edit Details", icon="GREASEPENCIL"
        )
        op.url = f"{paths.BLENDERKIT_USER_ASSETS_URL}/{props.asset_base_id}/?edit#"

        op = layout.operator(
            "object.blenderkit_upload", text="Reupload asset", icon="EXPORT"
        )
        op.asset_type = asset_type
        op.reupload = True

        op = layout.operator(
            "object.blenderkit_upload", text="Upload as new asset", icon="EXPORT"
        )
        op.asset_type = asset_type
        op.reupload = False

        # layout.label(text = 'asset id, overwrite only for reuploading')
        layout.label(text="asset has a version online.")
        # row = layout.row()
        # row.enabled = False
        # row.prop(props, 'asset_base_id', icon='FILE_TICK')
        # row = layout.row()
        # row.enabled = False
        # row.prop(props, 'id', icon='FILE_TICK')
    row = layout.row()
    if props.is_private == "PUBLIC" and props.category == "NONE":
        row.alert = True
    row.prop(props, "category")
    if props.category != "NONE" and props.subcategory != "EMPTY":
        row = layout.row()
        if props.is_private == "PUBLIC" and props.subcategory == "NONE":
            row.alert = True
        row.prop(props, "subcategory")
    if props.subcategory != "NONE" and props.subcategory1 != "EMPTY":
        row = layout.row()
        if props.is_private == "PUBLIC" and props.subcategory1 == "NONE":
            row.alert = True
        row.prop(props, "subcategory1")

    layout.prop(props, "is_private", expand=True)
    if props.is_private == "PUBLIC":
        layout.prop(props, "license")
        layout.prop(props, "is_free", expand=True)

    prop_needed(layout, props, "name", props.name)
    if props.is_private == "PUBLIC":
        prop_needed(layout, props, "description", props.description)
        prop_needed(layout, props, "tags", props.tags)
    else:
        layout.prop(props, "description")
        layout.prop(props, "tags")


def prop_needed(layout, props, name, value="", is_not_filled=""):
    row = layout.row()
    if value == is_not_filled:
        # row.label(text='', icon = 'ERROR')
        icon = "ERROR"
        row.alert = True
        row.prop(props, name)  # , icon=icon)
        row.alert = False
    else:
        # row.label(text='', icon = 'FILE_TICK')
        icon = None
        row.prop(props, name)


def draw_panel_hdr_upload(self, context):
    layout = self.layout
    ui_props = bpy.context.window_manager.blenderkitUI

    layout.prop(ui_props, "hdr_upload_image")

    hdr = utils.get_active_HDR()

    if hdr is not None:
        props = hdr.blenderkit

        layout = self.layout

        draw_upload_common(layout, props, "HDR", context)


def draw_panel_hdr_search(self, context):
    s = context.scene
    wm = context.window_manager
    props = wm.blenderkit_HDR
    ui_props = wm.blenderkitUI

    layout = self.layout
    row = layout.row()
    row.prop(props, "search_keywords", text="", icon="VIEWZOOM")
    draw_assetbar_show_hide(row, props)

    utils.label_multiline(layout, text=props.report)


def draw_panel_nodegroup_upload(self, context):
    layout = self.layout
    ui_props = bpy.context.window_manager.blenderkitUI
    layout.enabled = True

    layout.template_ID(ui_props, "nodegroup_upload")
    nodegroup = utils.get_active_nodegroup()

    if nodegroup is not None:
        props = nodegroup.blenderkit

        layout = self.layout

        draw_upload_common(layout, props, "NODEGROUP", context)
        layout.prop(props, "thumbnail")


def draw_panel_nodegroup_search(self, context):
    s = context.scene
    wm = context.window_manager
    props = wm.blenderkit_nodegroup

    layout = self.layout
    row = layout.row()
    row.prop(props, "search_keywords", text="", icon="VIEWZOOM")
    draw_assetbar_show_hide(row, props)

    utils.label_multiline(layout, text=props.report)


def draw_thumbnail_upload_panel(layout, props):
    tex = autothumb.get_texture_ui(props.thumbnail, ".upload_preview")
    if not tex or not tex.image:
        return
    box = layout.box()
    box.template_icon(icon_value=tex.image.preview.icon_id, scale=6.0)


def draw_panel_model_upload(self, context):
    ob = bpy.context.active_object
    while ob.parent is not None:
        ob = ob.parent
    props = ob.blenderkit

    layout = self.layout

    draw_upload_common(layout, props, "MODEL", context)

    col = layout.column()
    if props.is_generating_thumbnail:
        col.enabled = False

    draw_thumbnail_upload_panel(col, props)

    prop_needed(col, props, "thumbnail", props.thumbnail)
    if bpy.context.scene.render.engine in ACCEPTABLE_ENGINES:
        col.operator(
            "object.blenderkit_generate_thumbnail",
            text="Generate thumbnail",
            icon="IMAGE",
        )

    # row = layout.row(align=True)
    if props.is_generating_thumbnail:
        row = layout.row(align=True)
        row.label(text=props.thumbnail_generating_state)
        op = row.operator("object.kill_bg_process", text="", icon="CANCEL")
        op.process_source = "MODEL"
        op.process_type = "THUMBNAILER"
    elif props.thumbnail_generating_state != "":
        utils.label_multiline(layout, text=props.thumbnail_generating_state)

    # prop_needed(layout, props, 'style', props.style)
    # prop_needed(layout, props, 'production_level', props.production_level)
    layout.prop(props, "style")
    layout.prop(props, "production_level")

    layout.prop(props, "condition")
    layout.prop(props, "pbr")

    design_box = layout.box()
    design_box.alignment = "EXPAND"
    design_box.label(text="Design properties:")
    design_box.prop(props, "manufacturer")
    design_box.prop(props, "designer")
    design_box.prop(props, "design_collection")
    design_box.prop(props, "design_variant")
    design_box.prop(props, "use_design_year")
    if props.use_design_year:
        design_box.prop(props, "design_year")

    row = layout.row()
    row.prop(props, "work_hours")

    # CONTENT FLAGS
    content_flag_box = layout.box()
    content_flag_box.alignment = "EXPAND"
    content_flag_box.label(text="Sensitive Content Flags:")
    content_flag_box.prop(props, "sexualized_content")


def draw_panel_scene_upload(self, context):
    s = bpy.context.scene
    props = s.blenderkit

    layout = self.layout
    # if bpy.app.debug_value != -1:
    #     layout.label(text='Scene upload not Implemented')
    #     return
    draw_upload_common(layout, props, "SCENE", context)

    #    layout = layout.column()

    # row = layout.row()

    # if props.dimensions[0] + props.dimensions[1] == 0 and props.face_count == 0:
    #     icon = 'ERROR'
    #     layout.operator("object.blenderkit_auto_tags", text='Auto fill tags', icon=icon)
    # else:
    #     layout.operator("object.blenderkit_auto_tags", text='Auto fill tags')

    col = layout.column()
    # if props.is_generating_thumbnail:
    #     col.enabled = False
    draw_thumbnail_upload_panel(col, props)

    prop_needed(col, props, "thumbnail", props.has_thumbnail, False)
    # if bpy.context.scene.render.engine == 'CYCLES':
    #     col.operator("object.blenderkit_generate_thumbnail", text='Generate thumbnail', icon='IMAGE_COL')

    # row = layout.row(align=True)
    # if props.is_generating_thumbnail:
    #     row = layout.row(align=True)
    #     row.label(text = props.thumbnail_generating_state)
    #     op = row.operator('object.kill_bg_process', text="", icon='CANCEL')
    #     op.process_source = 'MODEL'
    #     op.process_type = 'THUMBNAILER'
    # elif props.thumbnail_generating_state != '':
    #    utils.label_multiline(layout, text = props.thumbnail_generating_state)

    layout.prop(props, "style")
    layout.prop(props, "production_level")
    layout.prop(props, "use_design_year")
    if props.use_design_year:
        layout.prop(props, "design_year")
    layout.prop(props, "condition")
    row = layout.row()
    row.prop(props, "work_hours")


def draw_assetbar_show_hide(layout, props):
    s = bpy.context.scene
    ui_props = bpy.context.window_manager.blenderkitUI

    if ui_props.assetbar_on:
        icon = "HIDE_OFF"
        ttip = "Click to Hide Asset Bar.\nShortcut: ;"
    else:
        icon = "HIDE_ON"
        ttip = "Click to Show Asset Bar.\nShortcut: ;"

    op = layout.operator("view3d.blenderkit_asset_bar_widget", text="", icon=icon)
    op.keep_running = False
    op.do_search = False
    op.tooltip = ttip


def draw_panel_model_search(self, context):
    wm = bpy.context.window_manager
    props = wm.blenderkit_models

    layout = self.layout

    row = layout.row()
    row.prop(props, "search_keywords", text="", icon="VIEWZOOM")
    draw_assetbar_show_hide(row, props)

    icon = "NONE"
    if props.report == "You need Full plan to get this item.":
        icon = "ERROR"
    utils.label_multiline(layout, text=props.report, icon=icon)
    if props.report == "You need Full plan to get this item.":
        layout.operator("wm.url_open", text="Get Full plan", icon="URL").url = (
            paths.BLENDERKIT_PLANS_URL
        )


def draw_panel_scene_search(self, context):
    wm = bpy.context.window_manager
    props = wm.blenderkit_scene
    layout = self.layout
    row = layout.row()
    row.prop(props, "search_keywords", text="", icon="VIEWZOOM")
    draw_assetbar_show_hide(row, props)
    utils.label_multiline(layout, text=props.report)
    layout.separator()


def draw_model_context_menu(self, context):
    # draw asset properties here
    layout = self.layout

    o = utils.get_active_model()
    if o.get("asset_data") is None:
        utils.label_multiline(
            layout,
            text="To upload this asset to BlenderKit, go to the Find and Upload Assets panel.",
        )
        layout.prop(o, "name")

    if o.get("asset_data") is not None:
        ad = o["asset_data"]
        layout.label(text=str(ad["name"]))
        if o.instance_type == "COLLECTION" and o.instance_collection is not None:
            layout.operator("object.blenderkit_bring_to_scene", text="Bring to scene")

        layout.label(text="Asset tools:")
        draw_asset_context_menu(self.layout, context, ad, from_panel=True)
        # if 'rig' in ad['tags']:
        #     # layout.label(text = 'can make proxy')
        #     layout.operator('object.blenderkit_make_proxy', text = 'Make Armature proxy')
    # fast upload, blocked by now
    # else:
    #     op = layout.operator("object.blenderkit_upload", text='Store as private', icon='EXPORT')
    #     op.asset_type = 'MODEL'
    #     op.fast = True
    # fun override project, not finished
    # layout.operator('object.blenderkit_color_corrector')


class VIEW3D_PT_blenderkit_model_properties(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_model_properties"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Selected Model"
    bl_context = "objectmode"

    @classmethod
    def poll(cls, context):
        if bpy.context.view_layer.objects.active is None:
            return False
        # if bpy.context.view_layer.objects.get('asset_data') is None:
        #     return False
        return True

    def draw(self, context):
        draw_model_context_menu(self, context)


class VIEW3D_MT_blenderkit_model_properties(Menu):
    bl_idname = "VIEW3D_MT_blenderkit_model_properties"
    bl_label = "Selected Model"

    def draw(self, context):
        draw_model_context_menu(self, context)


class NODE_PT_blenderkit_nodegroup_properties(Panel):
    bl_category = "BlenderKit"
    bl_idname = "NODE_PT_blenderkit_nodegroup_properties"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_label = "Selected Geonode tool"
    # bl_context = "editmode"

    @classmethod
    def poll(cls, context):
        if bpy.context.space_data.tree_type != "GeometryNodeTree":
            return False
        if not bpy.context.space_data.edit_tree:
            return False
        return bpy.context.space_data.edit_tree.is_tool

    def draw(self, context):
        # draw asset properties here
        layout = self.layout

        et = bpy.context.space_data.edit_tree
        if et.get("asset_data") is None:
            utils.label_multiline(
                layout,
                text="To upload this asset to BlenderKit, go to the Find and Upload Assets panel.",
            )
            layout.prop(et, "name")

        if et.get("asset_data") is not None:
            ad = et["asset_data"]
            layout.label(text=str(ad["name"]))

            layout.label(text="Asset tools:")
            draw_asset_context_menu(self.layout, context, ad, from_panel=True)


class NODE_PT_blenderkit_material_properties(Panel):
    bl_category = "BlenderKit"
    bl_idname = "NODE_PT_blenderkit_material_properties"
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_label = "Selected Material"
    bl_context = "objectmode"

    @classmethod
    def poll(cls, context):
        if bpy.context.space_data.tree_type != "ShaderNodeTree":
            return False
        p = (
            bpy.context.view_layer.objects.active is not None
            and bpy.context.active_object.active_material is not None
        )
        return p

    def draw(self, context):
        # draw asset properties here
        layout = self.layout

        m = bpy.context.active_object.active_material
        # o = bpy.context.active_object
        if m.get("asset_data") is None and m.blenderkit.id == "":
            utils.label_multiline(
                layout,
                text="To upload this asset to BlenderKit, go to the Find and Upload Assets panel.",
            )
            layout.prop(m, "name")

        if m.get("asset_data") is not None:
            ad = m["asset_data"]
            layout.label(text=str(ad["name"]))

            layout.label(text="Asset tools:")
            draw_asset_context_menu(self.layout, context, ad, from_panel=True)

        # fast upload, blocked by now
        # else:
        #     op = layout.operator("object.blenderkit_upload", text='Store as private', icon='EXPORT')
        #     op.asset_type = 'MODEL'
        #     op.fast = True
        # fun override project, not finished
        # layout.operator('object.blenderkit_color_corrector')


def draw_rating_asset(self, context, layout, index=0):
    ### draws single asset rating.
    # Todo: resolve multiple objects for display, now the props are on respective panel, which isn't great.

    col = layout.box()
    # split = layout.split(factor=0.5)
    # col1 = split.column()
    # col2 = split.column()
    # print('%s_search' % asset['asset_data']['assetType'])
    directory = paths.get_temp_dir("%s_search" % self.asset_data["assetType"])
    tpath = os.path.join(directory, self.asset_data["thumbnail_small"])
    for image in bpy.data.images:
        if image.filepath == tpath:
            # split = row.split(factor=1.0, align=False)
            col.template_icon(icon_value=image.preview.icon_id, scale=6.0)
            break
        # layout.label(text = '', icon_value=image.preview.icon_id, scale = 10)
    col.label(text=self.asset_data["name"])
    ratings.draw_ratings_menu(
        bpy.context.window_manager.blenderkit_ratings[index], context, col
    )


class VIEW3D_PT_blenderkit_ratings(Panel, ratings_utils.RatingProperties):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_ratings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Rate assets"
    bl_context = "objectmode"

    @classmethod
    def poll(cls, context):
        #
        p = bpy.context.view_layer.objects.active is not None
        return p

    def draw(self, context):
        # TODO make a list of assets inside asset appending code, to happen only when assets are added to the scene.
        # draw asset properties here
        layout = self.layout
        assets = ratings.get_assets_for_rating()
        if len(assets) > 0:
            utils.label_multiline(
                layout, text="Please help BlenderKit community by rating these assets:"
            )
            ad = assets[0].get("asset_data")
            reference = bpy.context.window_manager.blenderkit_ratings[0]
            reference.asset_data = ad
            reference.asset_id = self.asset_data["id"]
            reference.asset_type = reference.asset_data["assetType"]
            draw_rating_asset(reference, context, layout, index=0)


def draw_login_progress(layout):
    layout.label(text="Login through browser")
    layout.label(text="in progress.")
    layout.operator("wm.blenderkit_login_cancel", text="Cancel", icon="CANCEL")


class VIEW3D_PT_blenderkit_profile(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_profile"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = ""
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return True

    def draw_header(self, context):
        layout = self.layout
        layout.emboss = "NORMAL"
        user_preferences = bpy.context.preferences.addons[__package__].preferences
        if user_preferences.api_key != "":
            layout.label(text="BlenderKit Profile", icon="USER")
        else:
            layout.label(text="BlenderKit Login", icon="USER")

    def draw(self, context):
        layout = self.layout
        # don't draw when not online

        if not global_vars.CLIENT_RUNNING:
            layout.label(text="Client not running")
            return

        user_preferences = bpy.context.preferences.addons[__package__].preferences

        if user_preferences.login_attempt:
            draw_login_progress(layout)
            return

        if user_preferences.api_key != "":
            me = global_vars.BKIT_PROFILE
            if me is not None:
                # profile picture is retrieved from author's list, for coherency we store the profile images there.
                authors = global_vars.BKIT_AUTHORS
                me_id = int(me.id)
                if authors.get(me_id) is not None and authors[me_id].gravatarImg:
                    profile_img = autothumb.get_texture_ui(
                        authors[me_id].gravatarImg, ".blenderkit_profile_picture"
                    )
                    if profile_img and profile_img.image:
                        # draw the profile picture
                        box = layout.box()
                        box.template_icon(
                            icon_value=profile_img.image.preview.icon_id, scale=6.0
                        )

                # user name
                if len(me.firstName) > 0 or len(me.lastName) > 0:
                    layout.label(text=f"Me: {me.firstName} {me.lastName}")
                else:
                    layout.label(text=f"Me: {me.email}")
                # layout.label(text='Email: %s' % (me['email']))

                # plan information
                if me.currentPlanName is not None:
                    pcoll = icons.icon_collections["main"]
                    if me.currentPlanName == "Free":
                        my_icon = pcoll["free"]
                    else:
                        my_icon = pcoll["full"]

                    row = layout.row()
                    row.label(text="My plan:")
                    row.label(
                        text=f"{me.currentPlanName} plan", icon_value=my_icon.icon_id
                    )
                    if me.currentPlanName == "Free":
                        layout.operator(
                            "wm.url_open", text="Change plan", icon="URL"
                        ).url = paths.BLENDERKIT_PLANS_URL

                # STORAGE STATISTICS
                if (
                    me.sumPrivateAssetFilesSize != None
                    and me.remainingPrivateQuota != None
                ):
                    plan_storage = (
                        me.sumPrivateAssetFilesSize + me.remainingPrivateQuota
                    )
                    sum_str = utils.files_size_to_text(plan_storage)
                    row = layout.row()
                    row.label(text=f"Plan storage:")
                    row.label(text=sum_str)
                if me.remainingPrivateQuota is not None:
                    row = layout.row()
                    size_str = utils.files_size_to_text(me.remainingPrivateQuota)
                    row.label(text=f"Remaining:")
                    row.label(text=size_str)

            layout.operator("wm.url_open", text="See my uploads", icon="URL").url = (
                paths.BLENDERKIT_USER_ASSETS_URL
            )

        draw_login_buttons(layout)
        if user_preferences.api_key == "":
            layout.label(text="Log in to bookmark assets.")

        addon_updater_ops.update_notice_box_ui(self, context)


class MarkNotificationRead(bpy.types.Operator):
    """Mark notification as read here and also on BlenderKit server"""

    bl_idname = "wm.blenderkit_mark_notification_read"
    bl_label = "Mark notification as read"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    notification_id: bpy.props.IntProperty(  # type: ignore[valid-type]
        name="Id", description="notification id", default=-1
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        notifications = global_vars.DATA["bkit notifications"]
        for n in notifications["results"]:
            if n["id"] == self.notification_id:
                n["unread"] = 0
        comments_utils.check_notifications_read()
        client_lib.mark_notification_read(self.notification_id)
        return {"FINISHED"}


class MarkAllNotificationsRead(bpy.types.Operator):
    """Mark all notifications as read here and also on BlenderKit server"""

    bl_idname = "wm.blenderkit_mark_notifications_read_all"
    bl_label = "Mark all notifications as read"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        notifications = global_vars.DATA["bkit notifications"]
        for n in notifications.get("results"):
            if n["unread"] == 1:
                n["unread"] = 0
                client_lib.mark_notification_read(n["id"])

        comments_utils.check_notifications_read()
        return {"FINISHED"}


class NotificationOpenTarget(bpy.types.Operator):
    """Open notification target and mark notification as read"""

    bl_idname = "wm.blenderkit_open_notification_target"
    bl_label = ""
    bl_description = "Open notification target and mark notification as read"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    tooltip: bpy.props.StringProperty(default="Open a web page")  # type: ignore[valid-type]
    url: bpy.props.StringProperty(  # type: ignore[valid-type]
        default="Runs search and displays the asset bar at the same time"
    )
    notification_id: bpy.props.IntProperty(  # type: ignore[valid-type]
        name="Id", description="notification id", default=-1
    )

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

    def execute(self, context):
        bpy.ops.wm.blenderkit_mark_notification_read(
            notification_id=self.notification_id
        )
        bpy.ops.wm.url_open(url=self.url)
        return {"FINISHED"}


class UpvoteComment(bpy.types.Operator):
    """Up or downvote comment"""

    bl_idname = "wm.blenderkit_upvote_comment"
    bl_label = "BlenderKit up-downvote comment"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    asset_id: StringProperty(  # type: ignore[valid-type]
        name="Asset Base Id",
        description="Unique id of the asset (hidden)",
        default="",
        options={"SKIP_SAVE"},
    )

    comment_id: bpy.props.IntProperty(name="Id", description="comment id", default=-1)  # type: ignore[valid-type]

    flag: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="flag", description="Upvote/downvote comment", default="like"
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        user_preferences = bpy.context.preferences.addons[__package__].preferences
        api_key = user_preferences.api_key
        comments = comments_utils.get_comments_local(self.asset_id)
        profile = global_vars.BKIT_PROFILE
        for comment in comments:
            if comment["id"] != self.comment_id:
                continue
            comment["flags"].append({"flag": self.flag, "user": "", "id": profile.id})
            for flag in comment["flags"]:
                if flag["id"] == profile.id and flag["flag"] != self.flag:
                    comment["flags"].remove(flag)
                    break
        client_lib.feedback_comment(self.asset_id, self.comment_id, api_key, self.flag)
        return {"FINISHED"}


class SetPrivateComment(bpy.types.Operator):
    """Set comment private or public"""

    bl_idname = "wm.blenderkit_is_private_comment"
    bl_label = "BlenderKit set comment or thread private or public"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    asset_id: StringProperty(  # type: ignore[valid-type]
        name="Asset Base Id",
        description="Unique id of the asset (hidden)",
        default="",
        options={"SKIP_SAVE"},
    )

    comment_id: bpy.props.IntProperty(name="Id", description="comment id", default=-1)  # type: ignore[valid-type]

    is_private: bpy.props.BoolProperty(  # type: ignore[valid-type]
        name="Is private",
        description="set comment/thread private or public",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        user_preferences = bpy.context.preferences.addons[__package__].preferences
        api_key = user_preferences.api_key
        comments = comments_utils.get_comments_local(self.asset_id)
        if comments is not None:
            for comment in comments:
                if comment["id"] == self.comment_id:
                    comment["isPrivate"] = self.is_private
        client_lib.mark_comment_private(
            self.asset_id, self.comment_id, api_key, self.is_private
        )
        return {"FINISHED"}


# class DeleteComment(bpy.types.Operator):
#     """Delete comment on BlenderKit server"""
#     bl_idname = "wm.blenderkit_delete_comment"
#     bl_label = "BlenderKit delete comment"
#     bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
#
#     asset_id: StringProperty(
#         name="Asset Base Id",
#         description="Unique id of the asset (hidden)",
#         default="",
#         options={'SKIP_SAVE'})
#
#     comment_id: bpy.props.IntProperty(
#         name="Id",
#         description="comment id",
#         default=-1)
#
#     # flag: bpy.props.StringProperty(
#     #     name="flag",
#     #     description="Like/dislike comment",
#     #     default="like")
#
#     @classmethod
#     def poll(cls, context):
#         return True
#
#     def execute(self, context):
#         user_preferences = bpy.context.preferences.addons['blenderkit'].preferences
#         api_key = user_preferences.api_key
#         comments_utils.send_comment_delete_to_thread(asset_id=self.asset_id, comment_id=self.comment_id,# flag=self.flag,
#                                                    api_key=api_key)
#         return {'FINISHED'}


class PostComment(bpy.types.Operator):
    """Post a comment to BlenderKit server"""

    bl_idname = "wm.blenderkit_post_comment"
    bl_label = "BlenderKit post a new comment"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    asset_id: StringProperty(  # type: ignore[valid-type]
        name="Asset Base Id",
        description="Unique id of the asset (hidden)",
        default="",
        options={"SKIP_SAVE"},
    )

    comment_id: bpy.props.IntProperty(  # type: ignore[valid-type]
        name="Reply to Id", description="reply to comment id", default=0
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        user_preferences = bpy.context.preferences.addons[__package__].preferences
        ui_props = bpy.context.window_manager.blenderkitUI
        api_key = user_preferences.api_key

        # Store comment locally first for immediate display
        # need to fill in everything to satisfy the drawing of the comment
        comment_data = {
            "comment": ui_props.new_comment,
            "created": "just now",
            "author": global_vars.BKIT_PROFILE,
            "id": -1,  # Temporary ID until server response
            "level": self.comment_id != 0 and 1 or 0,  # If replying, set level 1
            "parentComment": self.comment_id if self.comment_id != 0 else None,
            "replies": [],
            "feedback": {"flags": [], "score": 0},
            "isPrivate": False,
            "canChangeIsPrivate": True,
            "userModerator": False,
            "isDeleted": False,
            "flags": [],  # For storing like/dislike flags
            "asset": self.asset_id,  # Reference to the asset being commented on
            "canEdit": True,  # User can edit their own new comments
            "submitDate": "just now",  # Server-generated timestamp
            "userName": global_vars.BKIT_PROFILE.firstName
            + " "
            + global_vars.BKIT_PROFILE.lastName,
        }
        comments = comments_utils.get_comments_local(self.asset_id) or []
        comments.append(comment_data)
        comments_utils.store_comments_local(self.asset_id, comments)

        # Send to server
        client_lib.create_comment(
            self.asset_id, ui_props.new_comment, api_key, self.comment_id
        )
        ui_props.new_comment = ""
        return {"FINISHED"}


def draw_notification(self, notification, width=600):
    layout = self.layout
    box = layout.box()
    actor = notification.get("actor", {}).get("string", "")
    verb = notification.get("verb", "")
    target = notification.get("target", {})
    if target is None:
        target = {}
    target_string = target.get("string", "")
    notification_string = notification.get("string", "")
    firstline = f"{actor} {verb} {target_string}"
    # firstline = f"{notification_string}"
    box1 = box.box()
    # row = box1.row()

    split_last = 0.7
    if notification["description"]:
        split_last = 0

    rows = utils.label_multiline(
        box1, text=firstline, width=width, split_last=split_last
    )

    if notification["description"]:
        rows = utils.label_multiline(
            box, text=notification["description"], width=width, split_last=0.7
        )

    if notification["target"]:
        # row = layout.row()
        # split = row.split(factor=.8)
        # split.label(text='')
        # split = split.split()
        # split = rows[-1].split(factor=0.8)
        # split = split.split()
        # split.alignment = 'RIGHT'
        # row = split.row(align = True)
        row = rows[-1]
        row = row.row(align=False)

        # row = row.split(factor = 0.7)

        op = row.operator(
            "wm.blenderkit_open_notification_target", text="Open page", icon="HIDE_OFF"
        )
        op.tooltip = "Open the browser on the asset page to comment"
        op.url = global_vars.SERVER + notification["target"]["url"]
        op.notification_id = notification["id"]
        # split =
        op = row.operator(
            "wm.blenderkit_mark_notification_read", text="", icon="CANCEL"
        )
        op.notification_id = notification["id"]


def draw_notifications(self, context, width=600):
    layout = self.layout
    notifications = global_vars.DATA.get("bkit notifications")
    if notifications is not None and notifications.get("count") > 0:
        row = layout.row()
        # row.alert = True
        split = row.split(factor=0.7)
        split.label(text="")
        split = split.split()
        split.operator(
            "wm.blenderkit_mark_notifications_read_all",
            text="Mark All Read",
            icon="CANCEL",
        )
        for notification in notifications["results"]:
            if notification["unread"] == 1:
                draw_notification(self, notification, width=width)


class LogoStatus(bpy.types.Operator):
    """BlenderKit status"""

    bl_idname = "wm.logo_status"
    bl_label = "BLENDERKIT STATUS"
    bl_options = {"REGISTER", "UNDO"}

    logo: StringProperty(name="logo", default="logo_offline")  # type: ignore[valid-type]


class ShowNotifications(bpy.types.Operator):
    """Show notifications"""

    bl_idname = "wm.show_notifications"
    bl_label = "Show BlenderKit notifications"
    bl_options = {"REGISTER", "UNDO"}

    notification_id: bpy.props.IntProperty(  # type: ignore[valid-type]
        name="Id", description="notification id", default=-1
    )

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        draw_notifications(self, context, width=600)

    def execute(self, context):
        wm = bpy.context.window_manager
        return wm.invoke_popup(self, width=600)


class VIEW3D_PT_blenderkit_notifications(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_notifications"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "BlenderKit Notifications"

    @classmethod
    def poll(cls, context):
        notifications = global_vars.DATA.get("bkit notifications")
        if notifications is not None and len(notifications["results"]) > 0:
            return True
        return False

    def draw(self, context):
        draw_notifications(self, context)


class VIEW3D_PT_blenderkit_login(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_login"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "BlenderKit Login"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        # don't draw when not online
        if not global_vars.CLIENT_RUNNING:
            layout.label(text="Client not running")
            return
        user_preferences = bpy.context.preferences.addons[__package__].preferences
        if user_preferences.login_attempt:
            draw_login_progress(layout)
            return

        draw_login_buttons(layout)


def draw_panel_material_upload(self, context):
    o = bpy.context.active_object
    mat = bpy.context.active_object.active_material

    props = mat.blenderkit
    layout = self.layout

    draw_upload_common(layout, props, "MATERIAL", context)

    # THUMBNAIL
    row = layout.column()
    if props.is_generating_thumbnail:
        row.enabled = False

    draw_thumbnail_upload_panel(row, props)

    prop_needed(row, props, "thumbnail", props.has_thumbnail, False)

    if bpy.context.scene.render.engine in ACCEPTABLE_ENGINES:
        layout.operator(
            "object.blenderkit_generate_material_thumbnail",
            text="Render thumbnail with Cycles",
            icon="EXPORT",
        )
    if props.is_generating_thumbnail:
        row = layout.row(align=True)
        row.label(text=props.thumbnail_generating_state, icon="RENDER_STILL")
        op = row.operator("object.kill_bg_process", text="", icon="CANCEL")
        op.process_source = "MATERIAL"
        op.process_type = "THUMBNAILER"
    elif props.thumbnail_generating_state != "":
        utils.label_multiline(layout, text=props.thumbnail_generating_state)

    layout.prop(props, "style")
    # if props.style == 'OTHER':
    #     layout.prop(props, 'style_other')
    # layout.prop(props, 'engine')
    # if props.engine == 'OTHER':
    #     layout.prop(props, 'engine_other')
    # layout.prop(props,'shaders')#TODO autofill on upload
    # row = layout.row()

    layout.prop(props, "pbr")
    layout.prop(props, "uv")
    layout.prop(props, "animated")
    layout.prop(props, "texture_size_meters")

    # tname = "." + bpy.context.active_object.active_material.name + "_thumbnail"
    # if props.has_thumbnail and bpy.data.textures.get(tname) is not None:
    #     row = layout.row()
    #     # row.scale_y = 1.5
    #     row.template_preview(bpy.data.textures[tname], preview_id='test')


def draw_panel_material_search(self, context):
    wm = context.window_manager
    props = wm.blenderkit_mat

    layout = self.layout
    row = layout.row()
    row.prop(props, "search_keywords", text="", icon="VIEWZOOM")
    draw_assetbar_show_hide(row, props)
    utils.label_multiline(layout, text=props.report)

    # layout.prop(props, 'search_style')F
    # if props.search_style == 'OTHER':
    #     layout.prop(props, 'search_style_other')
    # layout.prop(props, 'search_engine')
    # if props.search_engine == 'OTHER':
    #     layout.prop(props, 'search_engine_other')

    # draw_panel_categories(self, context)


def draw_panel_brush_upload(self, context):
    brush = utils.get_active_brush()
    if brush is not None:
        props = brush.blenderkit

        layout = self.layout

        draw_upload_common(layout, props, "BRUSH", context)


def draw_panel_brush_search(self, context):
    wm = context.window_manager
    props = wm.blenderkit_brush
    ui_props = wm.blenderkitUI

    layout = self.layout
    row = layout.row()
    row.prop(props, "search_keywords", text="", icon="VIEWZOOM")
    draw_assetbar_show_hide(row, props)

    utils.label_multiline(layout, text=props.report)


def draw_login_buttons(layout, invoke=False):
    user_preferences = bpy.context.preferences.addons[__package__].preferences

    if user_preferences.login_attempt:
        draw_login_progress(layout)
    else:
        if invoke:
            layout.operator_context = "INVOKE_DEFAULT"
        else:
            layout.operator_context = "EXEC_DEFAULT"
        if not utils.user_logged_in():
            layout.operator("wm.blenderkit_login", text="Login", icon="URL").signup = (
                False
            )
            layout.operator(
                "wm.blenderkit_login", text="Sign up", icon="URL"
            ).signup = True

        else:
            # layout.operator("wm.blenderkit_login", text="Login as someone else",
            #                 icon='URL').signup = False
            layout.operator("wm.blenderkit_logout", text="Logout", icon="URL")


class OpenBlenderKitDiscord(bpy.types.Operator):
    """Connect with our team, creators, and fellow users to discuss assets and the add-on"""

    bl_idname = "wm.blenderkit_join_discord"
    bl_label = "Open Discord"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        open_new_tab(global_vars.DISCORD_INVITE_URL)
        return {"FINISHED"}


class VIEW3D_PT_blenderkit_advanced_model_search(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_advanced_model_search"
    bl_parent_id = "VIEW3D_PT_blenderkit_unified"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Search filters"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        ui_props = bpy.context.window_manager.blenderkitUI
        if not global_vars.CLIENT_RUNNING:
            return False
        return ui_props.down_up == "SEARCH" and ui_props.asset_type == "MODEL"

    def draw_layout(self, layout):
        wm = bpy.context.window_manager
        props = wm.blenderkit_models
        ui_props = wm.blenderkitUI
        preferences = bpy.context.preferences.addons[__package__].preferences
        layout.separator()

        # layout.label(text = "common searches keywords:")
        # layout.prop(props, "search_global_keywords", text = "")
        # layout.prop(props, "search_modifier_keywords")
        # if props.search_engine == 'OTHER':
        #     layout.prop(props, "search_engine_keyword")
        row = layout.row()
        row.prop(ui_props, "search_bookmarks", text="Bookmarks", icon="BOOKMARKS")
        row.prop(ui_props, "own_only", icon="USER")
        row = layout.row()
        layout.prop(ui_props, "free_only")
        layout.prop(props, "search_style")

        layout.prop(props, "search_geometry_nodes", text="Geometry Nodes")

        # DESIGN YEAR
        layout.prop(props, "search_design_year", text="Designed in Year")
        if props.search_design_year:
            row = layout.row(align=True)
            row.prop(props, "search_design_year_min", text="Min")
            row.prop(props, "search_design_year_max", text="Max")

        # POLYCOUNT
        layout.prop(props, "search_polycount", text="Poly Count ")
        if props.search_polycount:
            row = layout.row(align=True)
            row.prop(props, "search_polycount_min", text="Min")
            row.prop(props, "search_polycount_max", text="Max")

        # TEXTURE RESOLUTION
        layout.prop(props, "search_texture_resolution", text="Texture Resolutions")
        if props.search_texture_resolution:
            row = layout.row(align=True)
            row.prop(props, "search_texture_resolution_min", text="Min")
            row.prop(props, "search_texture_resolution_max", text="Max")

        # FILE SIZE
        layout.prop(props, "search_file_size", text="File Size (MB)")
        if props.search_file_size:
            row = layout.row(align=True)
            row.prop(props, "search_file_size_min", text="Min")
            row.prop(props, "search_file_size_max", text="Max")

        # AGE
        layout.prop(
            props, "search_condition", text="Condition"
        )  # , text ='condition of object new/old e.t.c.')
        layout.prop(
            props, "search_animated", text="Animated"
        )  # , text ='condition of object new/old e.t.c.')
        layout.prop(
            ui_props, "quality_limit", slider=True
        )  # , text ='condition of object new/old e.t.c.')

        # layout.prop(props, "search_procedural", expand=True)
        # LICENSE
        layout.prop(ui_props, "search_license")

        # LIMIT BLENDER VERSION
        layout.prop(ui_props, "search_blender_version", text="Asset's Blender Version")
        if ui_props.search_blender_version:
            row = layout.row(align=True)
            row.prop(ui_props, "search_blender_version_min", text="Min")
            row.prop(ui_props, "search_blender_version_max", text="Max")

        # NSFW filter - in future we might add more subsets of what defines NSFW so users can tweak it, rn it is just sexualized content
        layout.prop(preferences, "nsfw_filter")

    def draw(self, context):
        self.draw_layout(self.layout)


class VIEW3D_PT_blenderkit_advanced_material_search(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_advanced_material_search"
    bl_parent_id = "VIEW3D_PT_blenderkit_unified"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Search filters"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        ui_props = bpy.context.window_manager.blenderkitUI
        if not global_vars.CLIENT_RUNNING:
            return False
        return ui_props.down_up == "SEARCH" and ui_props.asset_type == "MATERIAL"

    def draw_layout(self, layout):
        wm = bpy.context.window_manager
        props = wm.blenderkit_mat
        ui_props = wm.blenderkitUI

        layout.separator()

        row = layout.row()
        row.prop(ui_props, "search_bookmarks", text="Bookmarks", icon="BOOKMARKS")
        row.prop(ui_props, "own_only", icon="USER")

        layout.label(text="Texture:")
        col = layout.column()
        col.prop(props, "search_procedural", expand=True)

        if props.search_procedural == "TEXTURE_BASED":
            # TEXTURE RESOLUTION
            layout.prop(props, "search_texture_resolution", text="Texture Resolution")
            if props.search_texture_resolution:
                row = layout.row(align=True)
                row.prop(props, "search_texture_resolution_min", text="Min")
                row.prop(props, "search_texture_resolution_max", text="Max")

        # FILE SIZE
        layout.prop(props, "search_file_size", text="File size (MB)")
        if props.search_file_size:
            row = layout.row(align=True)
            row.prop(props, "search_file_size_min", text="Min")
            row.prop(props, "search_file_size_max", text="Max")
        layout.prop(ui_props, "quality_limit", slider=True)
        layout.prop(ui_props, "search_license")

    def draw(self, context):
        self.draw_layout(self.layout)


class VIEW3D_PT_blenderkit_advanced_scene_search(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_advanced_scene_search"
    bl_parent_id = "VIEW3D_PT_blenderkit_unified"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Search filters"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        s = context.scene
        ui_props = bpy.context.window_manager.blenderkitUI
        return ui_props.down_up == "SEARCH" and ui_props.asset_type == "SCENE"

    def draw_layout(self, layout):
        wm = bpy.context.window_manager
        props = wm.blenderkit_scene
        ui_props = wm.blenderkitUI

        layout.separator()

        row = layout.row()
        row.prop(ui_props, "search_bookmarks", text="Bookmarks", icon="BOOKMARKS")
        row.prop(ui_props, "own_only", icon="USER")

        layout.prop(ui_props, "free_only")
        layout.prop(ui_props, "quality_limit", slider=True)
        layout.prop(ui_props, "search_license")

    def draw(self, context):
        self.draw_layout(self.layout)


class VIEW3D_PT_blenderkit_advanced_HDR_search(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_advanced_HDR_search"
    bl_parent_id = "VIEW3D_PT_blenderkit_unified"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Search filters"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        ui_props = bpy.context.window_manager.blenderkitUI
        if not global_vars.CLIENT_RUNNING:
            return False
        return ui_props.down_up == "SEARCH" and ui_props.asset_type == "HDR"

    def draw(self, context):
        wm = context.window_manager
        props = wm.blenderkit_HDR
        ui_props = wm.blenderkitUI

        layout = self.layout
        layout.separator()

        row = layout.row()
        row.prop(ui_props, "search_bookmarks", text="Bookmarks", icon="BOOKMARKS")
        row.prop(ui_props, "own_only", icon="USER")
        layout.prop(ui_props, "free_only")
        layout.prop(props, "true_hdr")
        layout.prop(props, "search_texture_resolution", text="Texture Resolutions")
        if props.search_texture_resolution:
            row = layout.row(align=True)
            row.prop(props, "search_texture_resolution_min", text="Min")
            row.prop(props, "search_texture_resolution_max", text="Max")
        layout.prop(ui_props, "quality_limit", slider=True)
        layout.prop(ui_props, "search_license")


class VIEW3D_PT_blenderkit_advanced_brush_search(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_advanced_brush_search"
    bl_parent_id = "VIEW3D_PT_blenderkit_unified"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Search filters"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        ui_props = bpy.context.window_manager.blenderkitUI
        return ui_props.down_up == "SEARCH" and ui_props.asset_type == "BRUSH"

    def draw_layout(self, layout):
        wm = bpy.context.window_manager
        ui_props = wm.blenderkitUI

        layout.separator()

        row = layout.row()
        row.prop(ui_props, "search_bookmarks", text="Bookmarks", icon="BOOKMARKS")
        row.prop(ui_props, "own_only", icon="USER")
        layout.prop(ui_props, "free_only")
        layout.prop(ui_props, "quality_limit", slider=True)
        layout.prop(ui_props, "search_license")

    def draw(self, context):
        self.draw_layout(self.layout)


class VIEW3D_PT_blenderkit_categories(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_categories"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Categories"
    bl_parent_id = "VIEW3D_PT_blenderkit_unified"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        ui_props = bpy.context.window_manager.blenderkitUI
        if not global_vars.CLIENT_RUNNING:
            return False
        return ui_props.down_up == "SEARCH"

    def draw(self, context):
        # measure time since last dropdown activation/ mouse hover e.t.c.
        # this is then used in asset_bar_op.py to cancel asset drag drop if the time is too small and thus means double clicking.
        global last_time_dropdown_active
        last_time_dropdown_active = time.time()
        draw_panel_categories(self.layout, context)


def draw_scene_import_settings(self, context):
    wm = bpy.context.window_manager
    props = wm.blenderkit_scene
    layout = self.layout
    layout.prop(props, "switch_after_append")
    # layout.label(text='Import method:')
    row = layout.row()
    row.prop(props, "append_link", expand=True, icon_only=False)


class VIEW3D_PT_blenderkit_import_settings(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_import_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Import settings"
    bl_parent_id = "VIEW3D_PT_blenderkit_unified"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        ui_props = bpy.context.window_manager.blenderkitUI
        if not global_vars.CLIENT_RUNNING:
            return False
        if ui_props.asset_type not in ["MATERIAL", "MODEL", "SCENE", "HDR"]:
            return False
        return ui_props.down_up == "SEARCH"

    def draw(self, context):
        layout = self.layout

        s = context.scene
        wm = bpy.context.window_manager
        ui_props = bpy.context.window_manager.blenderkitUI
        preferences = bpy.context.preferences.addons[__package__].preferences

        if ui_props.asset_type == "MODEL":
            # noinspection PyCallByClass
            props = wm.blenderkit_models
            layout.prop(props, "randomize_rotation")
            if props.randomize_rotation:
                layout.prop(props, "randomize_rotation_amount")
            layout.prop(props, "perpendicular_snap")
            # if props.perpendicular_snap:
            #     layout.prop(props,'perpendicular_snap_threshold')

            layout.label(text="Import method:")
            row = layout.row()
            row.prop(props, "import_method", expand=True, icon_only=False)

        if ui_props.asset_type == "MATERIAL":
            props = wm.blenderkit_mat
            layout.prop(props, "automap")
            layout.label(text="Import method:")
            row = layout.row()

            row.prop(props, "import_method", expand=True, icon_only=False)
        if ui_props.asset_type == "SCENE":
            draw_scene_import_settings(self, context)

        if ui_props.asset_type == "HDR":
            props = wm.blenderkit_HDR

        if ui_props.asset_type in ["MATERIAL", "MODEL", "HDR"]:
            layout.prop(preferences, "unpack_files")
            layout.prop(preferences, "resolution")
        # layout.prop(props, 'unpack_files')


class VIEW3D_PT_blenderkit_unified(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_unified"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_options = {
        "HEADER_LAYOUT_EXPAND",
    }
    bl_label = ""

    def draw_header(self, context):
        layout = self.layout
        ui_props = bpy.context.window_manager.blenderkitUI
        pcoll = icons.icon_collections["main"]
        layout.label(
            text="Find and Upload Assets",
            icon_value=pcoll[ui_props.logo_status].icon_id,
        )

    def draw(self, context):
        ui_props = bpy.context.window_manager.blenderkitUI
        user_preferences = bpy.context.preferences.addons[__package__].preferences

        layout = self.layout
        # layout.prop_tabs_enum(ui_props, "asset_type", icon_only = True)
        if not global_vars.CLIENT_RUNNING:
            layout.label(text="Client not running")
            return

        row = layout.row()
        # row.scale_x = 1.6
        # row.scale_y = 1.6
        #
        row.prop(ui_props, "down_up", expand=True, icon_only=False)
        # row.label(text='')
        # row = row.split().row()
        # layout.alert = True
        # layout.alignment = 'CENTER'
        row = layout.row(align=True)
        row.scale_x = 1.6
        row.scale_y = 1.6
        # split = row.split(factor=.

        expand_icon = "TRIA_DOWN"
        if ui_props.asset_type_fold:
            expand_icon = "TRIA_RIGHT"
        row = layout.row()
        split = row.split(factor=0.15)
        split.prop(
            ui_props, "asset_type_fold", icon=expand_icon, icon_only=True, emboss=False
        )

        if ui_props.asset_type_fold:
            # expanded interface with names in column
            split = split.row()
            split.scale_x = 8
            split.scale_y = 1.6
            # split = row
            # split = layout.row()
        else:
            split = split.column()

        split.prop(
            ui_props, "asset_type", expand=True, icon_only=ui_props.asset_type_fold
        )
        # row = layout.column(align = False)
        # layout.prop(ui_props, 'asset_type', expand=False, text='')

        if user_preferences.login_attempt:
            draw_login_progress(layout)
            return

        if (
            len(user_preferences.api_key) < 20
            and user_preferences.download_counter > 20
        ):
            draw_login_buttons(layout)
            layout.separator()
        # if bpy.data.filepath == '':
        #     layout.alert = True
        #    utils.label_multiline(layout, text="It's better to save your file first.", width=w)
        #     layout.alert = False
        #     layout.separator()

        if ui_props.down_up == "SEARCH":
            self.draw_search(context, layout, ui_props)

        if ui_props.down_up == "UPLOAD":
            self.draw_upload(context, layout, ui_props)

    def draw_search(self, context, layout, ui_props):
        if utils.profile_is_validator():
            search_props = utils.get_search_props()
            layout.prop(search_props, "search_verification_status")
            layout.prop(search_props, "unrated_quality_only")
            layout.prop(search_props, "unrated_wh_only")

        if ui_props.asset_type == "MODEL":
            return draw_panel_model_search(self, context)

        if ui_props.asset_type == "SCENE":
            return draw_panel_scene_search(self, context)

        if ui_props.asset_type == "HDR":
            return draw_panel_hdr_search(self, context)

        if ui_props.asset_type == "MATERIAL":
            return draw_panel_material_search(self, context)

        if ui_props.asset_type == "BRUSH":
            if context.sculpt_object or context.image_paint_object:
                return draw_panel_brush_search(self, context)
            utils.label_multiline(
                layout,
                text="Switch to paint or sculpt mode.",
                width=context.region.width,
            )
            return

        if ui_props.asset_type == "NODEGROUP":
            return draw_panel_nodegroup_search(self, context)

    def draw_upload(self, context, layout, ui_props):
        # if not ui_props.assetbar_on:
        #     text = 'Show asset preview - ;'
        # else:
        #     text = 'Hide asset preview - ;'
        # op = layout.operator('view3d.blenderkit_asset_bar_widget', text=text, icon='EXPORT')
        # op.keep_running = False
        # op.do_search = False
        # op.tooltip = 'Show/Hide asset preview'
        if context.scene.render.engine not in ACCEPTABLE_ENGINES:
            rtext = (
                "Only Cycles, EEVEE and EEVEE (Legacy) render engines are currently supported. "
                "Please use Cycles for all assets you upload to BlenderKit."
            )
            utils.label_multiline(
                layout, rtext, icon="ERROR", width=context.region.width
            )
            return

        if ui_props.asset_type == "MODEL":
            if bpy.context.view_layer.objects.active is not None:
                return draw_panel_model_upload(self, context)
            layout.label(text="selet object to upload")
            return

        if ui_props.asset_type == "SCENE":
            return draw_panel_scene_upload(self, context)

        if ui_props.asset_type == "HDR":
            return draw_panel_hdr_upload(self, context)

        if ui_props.asset_type == "MATERIAL":
            if (bpy.context.view_layer.objects.active is not None) and (
                bpy.context.active_object.active_material is not None
            ):
                return draw_panel_material_upload(self, context)

            utils.label_multiline(
                layout,
                text="select object with material to upload materials",
                width=context.region.width,
            )
            return

        if ui_props.asset_type == "BRUSH":
            if context.sculpt_object or context.image_paint_object:
                return draw_panel_brush_upload(self, context)
            layout.label(text="Switch to paint or sculpt mode.")
            return

        if ui_props.asset_type == "NODEGROUP":
            return draw_panel_nodegroup_upload(self, context)


class BlenderKitWelcomeOperator(bpy.types.Operator):
    """Login online on BlenderKit webpage"""

    bl_idname = "wm.blenderkit_welcome"
    bl_label = "Welcome to BlenderKit!"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    step: IntProperty(  # type: ignore[valid-type]
        name="step", description="Tutorial Step", default=0, options={"SKIP_SAVE"}
    )

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        if self.step == 0:
            user_preferences = bpy.context.preferences.addons[__package__].preferences

            # message = "BlenderKit connects from Blender to an online, " \
            #           "community built shared library of models, " \
            #           "materials, and brushes. " \
            #           "Use addon preferences to set up where files will be saved in the Global directory setting."
            #
            # utils.label_multiline(layout, text=message, width=300)

            layout.template_icon(icon_value=self.img.preview.icon_id, scale=18)

            # utils.label_multiline(layout, text="\n Let's start by searching for some cool materials?", width=300)
            op = layout.operator(
                "wm.url_open", text="Watch Video Tutorial", icon="QUESTION"
            )
            op.url = paths.BLENDERKIT_MANUAL_URL

        else:
            message = "Operator Tutorial called with invalid step"

    def execute(self, context):
        if self.step == 0:
            ui_props = bpy.context.window_manager.blenderkitUI

            ui_props.asset_type = "MODEL"

            search.search(
                query={
                    "asset_type": "model",
                    "query": f"+is_free:true+score_gte:1000+order:-created",
                }
            )
        return {"FINISHED"}

    def invoke(self, context, event):
        user_preferences = bpy.context.preferences.addons[__package__].preferences
        if user_preferences.welcome_operator_counter > 10:
            return {"FINISHED"}
        user_preferences.welcome_operator_counter += 1

        wm = bpy.context.window_manager
        img = utils.get_thumbnail("intro.jpg")
        utils.img_to_preview(img, copy_original=True)
        self.img = img
        w, a, r = utils.get_largest_area(area_type="VIEW_3D")
        if a is not None:
            # Show regions in which the addon has UI
            a.spaces.active.show_region_ui = True
            a.spaces.active.show_region_tool_header = True

        return wm.invoke_props_dialog(self, width=500)


class OpenSystemDirectory(bpy.types.Operator):
    """Open directory in default system file explorer"""

    bl_idname = "wm.blenderkit_open_system_directory"
    bl_label = "Open system directory"
    bl_options = {"REGISTER", "UNDO"}
    directory: StringProperty(name="directory", default="")  # type: ignore[valid-type]

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        if not os.path.exists(self.directory):
            self.report({"ERROR"}, "Directory not found.")
            return {"CANCELLED"}
        paths.open_path_in_file_browser(self.directory)
        return {"FINISHED"}


class OpenAssetDirectory(OpenSystemDirectory):
    """Open directory containing the asset data"""

    bl_idname = "wm.blenderkit_open_asset_directory"
    bl_label = "Open asset directory"

    def execute(self, context):
        if not os.path.exists(self.directory):
            self.report({"ERROR"}, "Directory not found. Asset not downloaded yet.")
            return {"CANCELLED"}
        paths.open_path_in_file_browser(self.directory)
        return {"FINISHED"}


class OpenAddonDirectory(OpenSystemDirectory):
    """Open the directory in which the BlenderKit add-on is installed. Move one level up and delete it to hard-uninstall the add-on"""

    bl_idname = "wm.blenderkit_open_addon_directory"
    bl_label = "Open global directory"


class OpenGlobalDirectory(OpenSystemDirectory):
    """Open the BlenderKit's Global directory. This is the directory where BlenderKit stores downloaded assets. It also contains Client binary and log files"""

    bl_idname = "wm.blenderkit_open_global_directory"
    bl_label = "Open global directory"


class OpenClientLog(OpenSystemDirectory):
    """Open Log file of currently running Client. Client logs errors and other message in here. Inspect to see what is wrong with Client. Copy the contents when you make a bug report"""

    bl_idname = "wm.blenderkit_open_client_log"
    bl_label = "Open Client log"


class OpenTempDirectory(OpenSystemDirectory):
    """Open BlenderKit's temporary directory. This is the directory where thumbnails and other temporary files are stored"""

    bl_idname = "wm.blenderkit_open_temp_directory"
    bl_label = "Open temp directory"


def draw_asset_context_menu(
    layout, context: Context, asset_data: dict, from_panel: bool = False
):
    ui_props = context.window_manager.blenderkitUI  # type: ignore
    author_id = int(asset_data["author"].get("id"))
    layout.operator_context = "INVOKE_DEFAULT"

    if utils.user_logged_in():
        rating = ratings_utils.get_rating_local(asset_data["id"])
        if rating is None:
            rating = datas.AssetRating()
        if rating.bookmarks == 1:
            text = "Delete Bookmark"
            icon = "bookmark_full"
        else:
            text = "Bookmark"
            icon = "bookmark_empty"

        pcoll = icons.icon_collections["main"]
        op = layout.operator(
            "wm.blenderkit_bookmark_asset", text=text, icon_value=pcoll[icon].icon_id
        )
        op.asset_id = asset_data["id"]

    if from_panel:
        op = layout.operator(
            "wm.blenderkit_menu_rating_upload", text="Add Rating", icon="SOLO_ON"
        )
        op.asset_name = asset_data["name"]
        op.asset_id = asset_data["id"]
        op.asset_type = asset_data["assetType"]

    if from_panel and global_vars.BKIT_AUTHORS is not None and author_id is not None:
        author = global_vars.BKIT_AUTHORS.get(author_id)
        if author is not None:
            # utils.p('author:', a)
            op = layout.operator("wm.url_open", text="Open Author's Website")
            if author.aboutMeUrl:
                op.url = author.aboutMeUrl
            else:
                op.url = paths.get_author_gallery_url(author.id)
            op = layout.operator(
                "view3d.blenderkit_search", text="Show Assets By Author"
            )
            op.keywords = ""
            op.author_id = author_id

    op = layout.operator("view3d.blenderkit_search", text="Search Similar")
    op.esc = True
    op.tooltip = "Search for similar assets in the library.\nShortcut: hover over asset in asset bar and press 'S'."
    op.keywords = search.get_search_similar_keywords(asset_data)

    op = layout.operator("wm.url_open", text="See online", icon="URL")
    if (
        utils.user_is_owner(asset_data)
        and asset_data["verificationStatus"] != "validated"
    ):
        op.url = (
            f'{paths.BLENDERKIT_USER_ASSETS_URL}/{asset_data["assetBaseId"]}/?preview#'
        )
    else:
        op.url = paths.get_asset_gallery_url(asset_data["id"])
        # TODO this is where validator should be able to go and see non-validated the assets in gallery,
        # by now there's nowhere to go.

    # if asset_data["downloaded"] == 100:
    # enable opening the directory on drive
    dir_paths = paths.get_asset_directories(asset_data)
    if len(dir_paths) > 0 and os.path.exists(dir_paths[-1]):
        op = layout.operator(
            "wm.blenderkit_open_asset_directory",
            text="Open Directory",
            icon="FILE_FOLDER",
        )
        op.directory = dir_paths[-1]

    if asset_data.get("canDownload") != 0:
        if len(bpy.context.selected_objects) > 0 and ui_props.asset_type == "MODEL":
            aob = bpy.context.active_object
            if aob is None:
                aob = bpy.context.selected_objects[0]
            op = layout.operator(
                "scene.blenderkit_download", text="Replace Active Models"
            )
            op.tooltip = "Replace all selected models with this one"

            # this checks if the menu got called from right-click in assetbar(then index is 0 - x) or
            # from a panel(then replacement happens from the active model)
            if from_panel:
                # called from addon panel
                op.asset_base_id = asset_data["assetBaseId"]
            else:
                op.asset_index = ui_props.active_index

            # op.asset_type = ui_props.asset_type
            op.model_location = aob.location
            op.model_rotation = aob.rotation_euler
            op.target_object = aob.name  # type: ignore
            op.material_target_slot = aob.active_material_index
            op.replace = True
            op.replace_resolution = False

        # resolution replacement operator
        # if asset_data['downloaded'] == 100: # only show for downloaded/used assets
        # if ui_props.asset_type in ('MODEL', 'MATERIAL'):
        #     layout.menu(OBJECT_MT_blenderkit_resolution_menu.bl_idname)

        if (
            ui_props.asset_type in ("MODEL", "MATERIAL", "HDR")
            and utils.get_param(asset_data, "textureResolutionMax") is not None
            and utils.get_param(asset_data, "textureResolutionMax") > 512
        ):
            s = bpy.context.scene

            col = layout.column()
            col.operator_context = "INVOKE_DEFAULT"

            if from_panel:
                # Called from addon panel

                if (
                    asset_data.get("resolution")
                    or asset_data.get("available_resolutions") is not None
                ):
                    op = col.operator(
                        "scene.blenderkit_download", text="Replace asset resolution"
                    )
                    op.asset_base_id = asset_data["assetBaseId"]
                    if asset_data["assetType"] == "model":
                        o = utils.get_active_model()
                        op.model_location = o.location
                        op.model_rotation = o.rotation_euler
                        op.target_object = o.name
                        op.material_target_slot = o.active_material_index

                    elif asset_data["assetType"] == "material":
                        aob = bpy.context.active_object
                        op.model_location = aob.location
                        op.model_rotation = aob.rotation_euler
                        op.target_object = aob.name  # type: ignore
                        op.material_target_slot = aob.active_material_index
                    op.replace_resolution = True
                    op.replace = False

                    op.invoke_resolution = True
                    op.use_resolution_operator = True
                    op.max_resolution = asset_data.get(
                        "max_resolution", 0
                    )  # str(utils.get_param(asset_data, 'textureResolutionMax'))

            elif (
                asset_data["assetBaseId"] in s["assets used"].keys()  # type: ignore
                and asset_data["assetType"] != "hdr"
                and (
                    asset_data.get("resolution")
                    or asset_data.get("available_resolutions") is not None
                )
            ):
                # HDRs are excluded from replacement, since they are always replaced.
                # called from asset bar:
                op = col.operator(
                    "scene.blenderkit_download", text="Replace asset resolution"
                )

                op.asset_index = ui_props.active_index
                # op.asset_type = ui_props.asset_type
                op.replace_resolution = True
                op.replace = False
                op.invoke_resolution = True
                op.use_resolution_operator = True
                o = utils.get_active_model()
                if o and o.get("asset_data"):
                    if (
                        o["asset_data"]["assetBaseId"]
                        == global_vars.DATA["search results"][ui_props.active_index]
                    ):
                        op.model_location = o.location
                        op.model_rotation = o.rotation_euler
                    else:
                        op.model_location = (0, 0, 0)
                        op.model_rotation = (0, 0, 0)
                op.max_resolution = asset_data.get(
                    "max_resolution", 0
                )  # str(utils.get_param(asset_data, 'textureResolutionMax'))
            # print('operator res ', resolution)
            # op.resolution = resolution

    profile = global_vars.BKIT_PROFILE
    if profile is None:
        return

    # validation
    if (
        author_id == profile.id or utils.profile_is_validator()
    ):  # was not working due to wrong types
        layout.label(text="Management tools:")

        row = layout.row()
        row.operator_context = "INVOKE_DEFAULT"
        op = layout.operator(
            "wm.blenderkit_fast_metadata", text="Edit Metadata", icon="GREASEPENCIL"
        )
        op.asset_id = asset_data["id"]
        op.asset_type = asset_data["assetType"]

        if author_id == str(profile.id):
            row.operator_context = "EXEC_DEFAULT"
            op = layout.operator(
                "wm.blenderkit_url",
                text="Edit Metadata (browser)",
                icon="GREASEPENCIL",
            )
            op.url = (
                f'{paths.BLENDERKIT_USER_ASSETS_URL}/{asset_data["assetBaseId"]}/?edit#'
            )

        row.operator_context = "INVOKE_DEFAULT"

        if asset_data["assetType"] == "model":
            op = layout.operator(
                "object.blenderkit_regenerate_thumbnail",
                text="Regenerate thumbnail",
            )
            op.asset_index = ui_props.active_index
        elif asset_data["assetType"] == "material":
            op = layout.operator(
                "object.blenderkit_regenerate_material_thumbnail",
                text="Regenerate thumbnail",
            )
            op.asset_index = ui_props.active_index
            # op.asset_id = asset_data['id']
            # op.asset_type = asset_data['assetType']

    if author_id == profile.id:  # was not working because of wrong types
        row = layout.row()
        row.operator_context = "INVOKE_DEFAULT"
        op = row.operator("object.blenderkit_change_status", text="Delete")
        op.asset_id = asset_data["id"]
        op.state = "deleted"
        op.original_state = asset_data["verificationStatus"]

    if utils.profile_is_validator():
        layout.label(text="Dev Tools:")
        op = layout.operator(
            "object.blenderkit_print_asset_debug", text="Print asset debug"
        )
        op.asset_id = asset_data["id"]


# def draw_asset_resolution_replace(self, context, resolution):
#     layout = self.layout
#     ui_props = bpy.context.window_manager.blenderkitUI
#
#     op = layout.operator('scene.blenderkit_download', text=resolution)
#     if ui_props.active_index == -3:
#         # This happens if the command is called from addon panel
#         o = utils.get_active_model()
#         op.asset_base_id = o['asset_data']['assetBaseId']
#
#     else:
#         op.asset_index = ui_props.active_index
#
#         op.asset_type = ui_props.asset_type
#     if len(bpy.context.selected_objects) > 0:  # and ui_props.asset_type == 'MODEL':
#         aob = bpy.context.active_object
#         op.model_location = aob.location
#         op.model_rotation = aob.rotation_euler
#         op.target_object = aob.name
#         op.material_target_slot = aob.active_material_index
#     op.replace_resolution = True
#     print('operator res ', resolution)
#     op.resolution = resolution


# class OBJECT_MT_blenderkit_resolution_menu(bpy.types.Menu):
#     bl_label = "Replace Asset Resolution"
#     bl_idname = "OBJECT_MT_blenderkit_resolution_menu"
#
#     def draw(self, context):
#         ui_props = context.window_manager.blenderkitUI
#
#         # sr = global_vars.DATA['search results']
#
#         # sr = global_vars.DATA['search results']
#         # asset_data = sr[ui_props.active_index]
#
#         for k in resolutions.resolution_props_to_server.keys():
#             draw_asset_resolution_replace(self, context, k)


class OBJECT_MT_blenderkit_asset_menu(bpy.types.Menu):
    bl_label = "Asset options:"
    bl_idname = "OBJECT_MT_blenderkit_asset_menu"

    def draw(self, context):
        ui_props = context.window_manager.blenderkitUI

        sr = global_vars.DATA["search results"]
        asset_data = sr[ui_props.active_index]
        draw_asset_context_menu(self.layout, context, asset_data, from_panel=False)


def numeric_to_str(s):
    if s:
        if s < 1:
            s = str(round(s, 1))
        else:
            s = str(round(s))
    else:
        s = "-"
    return s


def push_op_left(layout, strength=3):
    for a in range(0, strength):
        layout.label(text="")


def label_or_url_or_operator(
    layout,
    text="",
    tooltip="",
    url="",
    operator=None,
    operator_kwargs={},
    icon_value=None,
    icon=None,
    emboss=False,
):
    """automatically switch between different layout options for linking or tooltips"""
    layout.emboss = "NORMAL" if emboss else "NONE"

    if operator is not None:
        if icon:
            op = layout.operator(operator, text=text, icon=icon, emboss=emboss)
        elif icon_value:
            op = layout.operator(
                operator, text=text, icon_value=icon_value, emboss=emboss
            )
        else:
            op = layout.operator(operator, text=text, emboss=emboss)
        for kwarg in operator_kwargs.keys():
            setattr(op, kwarg, operator_kwargs[kwarg])
        push_op_left(layout, strength=2)

        return
    if url != "":
        if icon:
            op = layout.operator(
                "wm.blenderkit_url", text=text, icon=icon, emboss=emboss
            )
        elif icon_value:
            op = layout.operator(
                "wm.blenderkit_url", text=text, icon_value=icon_value, emboss=emboss
            )
        else:
            op = layout.operator("wm.blenderkit_url", text=text, emboss=emboss)
        op.url = url
        op.tooltip = tooltip
        push_op_left(layout, strength=5)

        return
    if tooltip != "":
        if icon:
            op = layout.operator(
                "wm.blenderkit_tooltip", text=text, icon=icon, emboss=emboss
            )
        elif icon_value:
            op = layout.operator(
                "wm.blenderkit_tooltip", text=text, icon_value=icon_value, emboss=emboss
            )
        else:
            op = layout.operator("wm.blenderkit_tooltip", text=text, emboss=emboss)
        op.tooltip = tooltip

        # these are here to move the text to left, since operators can only center text by default
        push_op_left(layout, strength=3)
        return
    if icon:
        layout.label(text=text, icon=icon)
    elif icon_value:
        layout.label(text=text, icon_value=icon_value)
    else:
        layout.label(text=text)


class AssetPopupCard(bpy.types.Operator, ratings_utils.RatingProperties):
    """Generate Cycles thumbnail for model assets"""

    bl_idname = "wm.blenderkit_asset_popup"
    bl_label = "BlenderKit asset popup"

    width = 800

    @classmethod
    def poll(cls, context):
        return True

    def draw_menu(self, context, layout):
        # layout = layout.column()
        draw_asset_context_menu(layout, context, self.asset_data, from_panel=False)

    def draw_property(
        self,
        layout,
        left,
        right,
        icon=None,
        icon_value=None,
        url="",
        tooltip="",
        operator=None,
        operator_kwargs={},
        emboss=False,
    ):
        right = str(right)
        row = layout.row()
        split = row.split(factor=0.35)
        split.alignment = "RIGHT"
        split.label(text=left)
        split = split.split()
        split.alignment = "LEFT"
        # split for questionmark:
        # if url != "" and not emboss:
        split = split.split(factor=0.9)
        split.alignment = "LEFT"
        label_or_url_or_operator(
            split,
            text=right,
            tooltip=tooltip,
            url=url,
            operator=operator,
            operator_kwargs=operator_kwargs,
            icon_value=icon_value,
            icon=icon,
            emboss=emboss,
        )
        # additional questionmark icon where it's important?
        # Embossed elements are visibly clickable, so we don't need the questionmark icon
        if url != "" and not emboss:
            split = split.split()
            op = split.operator("wm.blenderkit_url", text="", icon="QUESTION")
            op.url = url
            op.tooltip = tooltip

    def draw_asset_parameter(
        self, layout, key="", pretext="", do_search=False, decimal=True
    ):
        parameter = utils.get_param(self.asset_data, key)
        if parameter == None:
            return
        if type(parameter) == int:
            if decimal:
                parameter = f"{parameter:,d}"
            else:
                parameter = f"{parameter}"
        elif type(parameter) == float:
            parameter = f"{parameter:,.1f}"
        if do_search:
            kwargs = {
                "esc": True,
                "keywords": f"+{key}:{parameter}",
                "tooltip": f"search by {parameter}",
            }
            # search gets auto emboss
            self.draw_property(
                layout,
                pretext,
                parameter,
                operator="view3d.blenderkit_search",
                operator_kwargs=kwargs,
                emboss=True,
            )
        else:
            self.draw_property(layout, pretext, parameter)

    def draw_description(self, layout, width=250):
        if len(self.asset_data["description"]) > 0:
            box = layout.box()
            box.scale_y = 0.4
            box.label(text="Description")
            box.separator()
            link_more = utils.label_multiline(
                box, self.asset_data["description"], width=width, max_lines=10
            )
            if link_more:
                row = box.row()
                row.scale_y = 2
                op = row.operator(
                    "wm.blenderkit_url", text="See full description", icon="URL"
                )
                op.url = paths.get_asset_gallery_url(self.asset_data["assetBaseId"])
                op.tooltip = "Read full description on website"
            box.separator()

    def draw_properties(self, layout, width=250):
        # if type(self.asset_data['parameters']) == list:
        #     mparams = utils.params_to_dict(self.asset_data['parameters'])
        # else:
        #     mparams = self.asset_data['parameters']
        mparams = self.asset_data["dictParameters"]

        pcoll = icons.icon_collections["main"]

        box = layout.box()

        box.scale_y = 0.6
        box.label(text="Properties")
        box.separator()

        if self.asset_data.get("license") == "cc_zero":
            t = "CC Zero          "
            icon = pcoll["cc0"]
        else:
            t = "Royalty free"
            icon = pcoll["royalty_free"]
        self.draw_property(
            box,
            "License",
            t,
            # icon_value=icon.icon_id,
            url=f"{global_vars.SERVER}/docs/licenses/",
            tooltip="All BlenderKit assets are available for commercial use. \n"
            "Click to read more about BlenderKit licenses on the website",
        )

        if upload.can_edit_asset(asset_data=self.asset_data):
            icon = pcoll[self.asset_data["verificationStatus"]]
            verification_status_tooltips = {
                "uploading": "Your asset got stuck during upload. Probably, your file was too large "
                "or your connection too slow or interrupting. If you have repeated issues, "
                "please contact us and let us know, it might be a bug",
                "uploaded": "Your asset uploaded successfully. Yay! If it's public, "
                "it's awaiting validation. If it's private, use it",
                "on_hold": "Your asset needs some (usually smaller) fixes, "
                "so we can make it public for everybody."
                " Please check validator comments under your asset to see the feedback "
                "that we send to every creator personally",
                "rejected": "The asset has serious quality issues, "
                "and it's probable that it might be good to start "
                "all over again or try with something simpler. "
                "You also get personal feedback into your e-mail, "
                "since we believe that together, we can all learn "
                "to become awesome 3D artists",
                "deleted": "You deleted this asset",
                "validated": "Your asset passed our validation process, "
                "and is now available to BlenderKit users",
            }
            self.draw_property(
                box,
                "Verification",
                self.asset_data["verificationStatus"],
                icon_value=icon.icon_id,
                url=f"{global_vars.SERVER}/docs/validation-status/",
                tooltip=verification_status_tooltips[
                    self.asset_data["verificationStatus"]
                ],
            )
        # resolution/s
        resolution = utils.get_param(self.asset_data, "textureResolutionMax")
        available_res = self.asset_data.get("available_resolutions")
        fs = self.asset_data["files"]

        if resolution is not None or len(available_res) > 0:
            if resolution is None:
                # this should get removed once all assets that have texture have proper resolution parameter fixed
                # by now part of assets that have texture don't have texture resolution marked
                ress = f"{int(round(available_res[-1] / 1024, 0))}K"
            else:
                ress = f"{int(round(resolution / 1024, 0))}K"
            self.draw_property(
                box,
                "Resolution",
                ress,
                tooltip="Maximal resolution of textures in this asset.\n"
                "Most texture asset have also lower resolutions generated.\n"
                "Go to BlenderKit add-on import settings to set default resolution",
            )
            # this would normally show only when theres's texture resolution parameter.
            # but this parameter wasn't always uploaded correctly, that's why we need to check also for others
            if fs and len(fs) > 2:  # and utils.profile_is_validator():
                resolutions = ""
                list.sort(fs, key=lambda f: f["fileType"])
                for f in fs:
                    if f["fileType"].find("resolution") > -1:
                        resolutions += f["fileType"][11:] + " "
                resolutions = resolutions.replace("_", ".")
                self.draw_property(box, "Generated res", resolutions)

        self.draw_asset_parameter(
            box, key="designer", pretext="Designer", do_search=True
        )
        self.draw_asset_parameter(
            box, key="manufacturer", pretext="Manufacturer", do_search=True
        )
        self.draw_asset_parameter(
            box, key="designCollection", pretext="Collection", do_search=True
        )
        self.draw_asset_parameter(box, key="designVariant", pretext="Variant")
        self.draw_asset_parameter(
            box, key="designYear", pretext="Design year", decimal=False
        )

        self.draw_asset_parameter(box, key="faceCount", pretext="Face count")
        # self.draw_asset_parameter(box, key='thumbnailScale', pretext='Preview scale')
        # self.draw_asset_parameter(box, key='purePbr', pretext='Pure PBR')
        # self.draw_asset_parameter(box, key='productionLevel', pretext='Readiness')
        # self.draw_asset_parameter(box, key='condition', pretext='Condition')
        if utils.profile_is_validator():
            self.draw_asset_parameter(box, key="materialStyle", pretext="Style")
            self.draw_asset_parameter(box, key="modelStyle", pretext="Style")

        if utils.get_param(self.asset_data, "dimensionX"):
            t = utils.fmt_dimensions(mparams)
            self.draw_property(box, "Size", t)
        if self.asset_data.get("filesSize"):
            fs = self.asset_data["filesSize"] * 1024
            # multiply because the number is reduced when search is done to avoind C intiger limit with large files
            fsmb = fs // (1024 * 1024)
            fskb = fs % 1024
            if fsmb == 0:
                self.draw_property(box, "Original size", f"{fskb} KB")
            else:
                self.draw_property(box, "Original size", f"{fsmb} MB")
        # Tags section
        # row = box.row()
        # letters_on_row = 0
        # max_on_row = width / 10
        # for tag in self.asset_data['tags']:
        #     if tag in ('manifold', 'uv', 'non-manifold'):
        #         # these are sometimes accidentally stored in the lib
        #         continue
        #
        #     # row.emboss='NONE'
        #     # we need to split wisely
        #     remaining_row = (max_on_row - letters_on_row) / max_on_row
        #     split_factor = (len(tag) / max_on_row) / remaining_row
        #     row = row.split(factor=split_factor)
        #     letters_on_row += len(tag)
        #     if letters_on_row > max_on_row:
        #         letters_on_row = len(tag)
        #         row = box.row()
        #         remaining_row = (max_on_row - letters_on_row) / max_on_row
        #         split_factor = (len(tag) / max_on_row) / remaining_row
        #         row = row.split(factor=split_factor)
        #
        #     op = row.operator('wm')
        #     op = row.operator('view3d.blenderkit_search', text=tag)
        #     op.tooltip = f'Search items with tag {tag}'
        #     # build search string from description and tags:
        #     op.keywords = f'+tags:{tag}'

        # self.draw_property(box, 'Tags', self.asset_data['tags']) #TODO make them clickable!

        # Free/Full plan or private Access
        plans_tooltip = (
            "BlenderKit has 2 plans:\n"
            "  *  Free plan - more than 50% of all assets\n"
            "  *  Full plan - unlimited access to everything\n"
            "Click to go to subscriptions page"
        )
        if self.asset_data["isPrivate"]:
            t = "Private"
            self.draw_property(box, "Access", t, icon="LOCKED")
        elif self.asset_data["isFree"]:
            t = "Free plan"
            icon = pcoll["free"]
            self.draw_property(
                box,
                "Access",
                t,
                icon_value=icon.icon_id,
                tooltip=plans_tooltip,
                url=paths.BLENDERKIT_PLANS_URL,
            )
        else:
            t = "Full plan"
            icon = pcoll["full"]
            self.draw_property(
                box,
                "Access",
                t,
                icon_value=icon.icon_id,
                tooltip=plans_tooltip,
                url=paths.BLENDERKIT_PLANS_URL,
            )

        if utils.profile_is_validator():
            date = self.asset_data["created"][:10]
            date = f"{date[8:10]}. {date[5:7]}. {date[:4]}"
            self.draw_property(box, "Created", date)
            self.draw_property(
                box,
                "Sexualized:",
                self.asset_data.get("dictParameters", {}).get("sexualizedContent"),
            )

        from_newer, difference = utils.asset_from_newer_blender_version(self.asset_data)
        if from_newer:
            if difference == "major":
                warning = (
                    f"{self.asset_data['sourceAppVersion']} - newer major version!"
                )
            elif difference == "minor":
                warning = (
                    f"{self.asset_data['sourceAppVersion']} - newer minor version!"
                )
            else:
                warning = (
                    f"{self.asset_data['sourceAppVersion']} - slightly newer version."
                )
            box.alert = True
            self.draw_property(
                box,
                "Blender version",
                warning,
                icon="ERROR",
            )
            box.alert = False
        else:
            self.draw_property(
                box,
                "Blender version",
                self.asset_data["sourceAppVersion"],
                # icon='ERROR',
                # tooltip='The version this asset was created in.',
            )

        # Add TwinBru specific parameters for material assets
        # only if they have twinbruReference in the dictparameters
        if self.asset_data.get("dictParameters").get("twinbruReference"):
            box.separator()
            box.label(text="TwinBru physical material categories")

            self.draw_asset_parameter(
                box,
                key="twinBruCatEndUse",
                pretext="End Use",
                do_search=True,
            )
            self.draw_asset_parameter(
                box,
                key="twinBruColourType",
                pretext="Colour Type",
                do_search=True,
            )
            self.draw_asset_parameter(
                box,
                key="twinBruCharacteristics",
                pretext="Characteristics",
                do_search=True,
            )
            self.draw_asset_parameter(
                box,
                key="twinBruDesignType",
                pretext="Design Type",
                do_search=True,
            )

        # Product Link for assets that have it.
        if self.asset_data.get("dictParameters").get("productLink"):
            self.draw_property(
                box,
                "Product Link",
                "View on manufacturer's website",
                url=self.asset_data["dictParameters"]["productLink"],
                icon="URL",
                emboss=True,
            )

        box.separator()

    def draw_author_area(self, context, layout, width=330):
        self.draw_author(context, layout, width=width)

    def draw_author(
        self, context: bpy.types.Context, layout: bpy.types.UILayout, width: int = 330
    ):
        image_split = 0.25
        text_width = width
        authors = global_vars.BKIT_AUTHORS
        author_id = int(self.asset_data["author"]["id"])
        author = authors.get(author_id)
        if author is None:
            return

        row = layout.row()
        author_box = row.box()
        author_box.scale_y = 0.6  # get text lines closer to each other
        author_box.label(text="Author")  # just one extra line to give spacing
        if hasattr(self, "gimg"):
            author_left = author_box.split(factor=image_split)
            author_left.template_icon(icon_value=self.gimg.preview.icon_id, scale=7)
            self.gimg.gl_touch()

            text_area = author_left.split()
            text_width = int(text_width * (1 - image_split))
        else:
            text_area = author_box

        author_right = text_area.column()
        row = author_right.row()
        col = row.column()

        utils.label_multiline(col, text=author.tooltip, width=text_width)
        # check if author didn't fill any data about himself and prompt him if that's the case
        if utils.user_is_owner(asset_data=self.asset_data) and not author.aboutMe:
            row = col.row()
            row.enabled = False
            row.label(text="Please introduce yourself to the community!")

            op = col.operator("wm.blenderkit_url", text="Edit your profile")
            op.url = f"{global_vars.SERVER}/profile"  # type: ignore[attr-defined]
            op.tooltip = "Edit your profile on BlenderKit webpage"  # type: ignore[attr-defined]

        pcoll = icons.icon_collections["main"]

        button_row = author_box.row()
        button_row.scale_y = 2.0

        # AUTHOR's ASSETS SEARCH
        op = button_row.operator(
            "view3d.blenderkit_search", text="Find Assets By Author", icon="VIEWZOOM"
        )
        op.tooltip = "Search all assets by this author.\nShortcut: Hover over the asset in the asset bar and press 'A'."  # type: ignore[attr-defined]
        op.esc = True  # type: ignore[attr-defined]
        op.keywords = ""  # type: ignore[attr-defined]
        op.author_id = self.asset_data["author"]["id"]  # type: ignore[attr-defined]

        button_row = button_row.row(align=True)

        # AUTHOR's BLENDERKIT PROFILE
        url = paths.get_author_gallery_url(author.id)
        tooltip = "Go to author's profile on BlenderKit web.\nShortcut: Hover over asset in the asset bar and press 'P'."
        icon_value = pcoll["logo"].icon_id
        op = button_row.operator("wm.blenderkit_url", text="", icon_value=icon_value)
        op.url = url  # type: ignore[attr-defined]
        op.tooltip = tooltip  # type: ignore[attr-defined]

        # ABOUT ME WEBPAGE
        text = None
        if author.aboutMeUrl:
            text = utils.remove_url_protocol(author.aboutMeUrl)
            text = utils.shorten_text(text, 45)
            op = button_row.operator("wm.blenderkit_url", text="", icon="URL")
            op.url = author.aboutMeUrl  # type: ignore[attr-defined]
            op.tooltip = f"Go to author's personal Webpage: {author.aboutMeUrl}\nShortcut: Hover over asset in the asset bar and press 'W'."  # type: ignore[attr-defined]

        # SOCIAL NETWORKS
        social_networks = author.socialNetworks
        for social_network in social_networks:
            url = social_network.url
            tooltip = f"Go to {social_network.name} profile"

            icon_value = pcoll[f"logo_{social_network.name.lower()}"].icon_id
            if url is None or text is None:
                continue

            op = button_row.operator(
                "wm.blenderkit_url", text="", icon_value=icon_value
            )
            op.url = url  # type: ignore[attr-defined]
            op.tooltip = tooltip  # type: ignore[attr-defined]

    def draw_thumbnail_box(self, layout, width=250):
        layout.emboss = "NORMAL"

        box_thumbnail = layout.box()

        box_thumbnail.scale_y = 0.4
        box_thumbnail.template_icon(
            icon_value=self.img.preview.icon_id, scale=width * 0.12
        )
        self.img.gl_touch()

        # op = row.operator('view3d.asset_drag_drop', text='Drag & Drop from here', depress=True)
        # From here on, only ratings are drawn, which won't be displayed for private assets from now on.

        rc = self.asset_data.get("ratingsCount")

        if (
            not self.asset_data["isPrivate"]
            and rc.get("quality") is not None
            and rc.get("workingHours") is not None
        ):
            row = box_thumbnail.row()
            row.alignment = "EXPAND"

            # display_ratings = can_display_ratings(self.asset_data)
            show_rating_threshold = 0
            show_rating_prompt_threshold = 5

            if rc:
                rcount = min(rc["quality"], rc["workingHours"])
            else:
                rcount = 0
            if rcount >= show_rating_threshold or upload.can_edit_asset(
                asset_data=self.asset_data
            ):
                s = numeric_to_str(self.asset_data["score"])
                q = numeric_to_str(self.asset_data["ratingsAverage"].get("quality"))
                c = numeric_to_str(self.asset_data["ratingsMedian"].get("workingHours"))
            else:
                s = "-"
                q = "-"
                c = "-"

            pcoll = icons.icon_collections["main"]

            row.emboss = "NONE"
            op = row.operator(
                "wm.blenderkit_tooltip", text=str(s), icon_value=pcoll["trophy"].icon_id
            )
            op.tooltip = (
                "Asset score calculated from user ratings. \n\n"
                "Score = average quality × median complexity × 10*\n\n *Happiness multiplier"
            )
            row.label(text="   ")

            tooltip_extension = f".\n\nRatings results are shown for assets with more than {show_rating_threshold} ratings"
            op = row.operator("wm.blenderkit_tooltip", text=str(q), icon="SOLO_ON")
            op.tooltip = (
                f"Quality, average from {rc['quality']} rating{'' if rc['quality'] == 1 else 's'}"
                f"{tooltip_extension if rcount <= show_rating_threshold else ''}"
            )
            row.label(text="   ")

            op = row.operator(
                "wm.blenderkit_tooltip",
                text=str(c),
                icon_value=pcoll["dumbbell"].icon_id,
            )
            op.tooltip = (
                f"Complexity, median from {rc['workingHours']} rating{'' if rc['workingHours'] == 1 else 's'}"
                f"{tooltip_extension if rcount <= show_rating_threshold else ''}"
            )

            if (
                rcount <= show_rating_prompt_threshold
                and self.rating_quality == 0
                and self.rating_work_hours == 0
            ):
                # if the asset has less than 5 ratings, and the user hasn't rated it yet, prompt them to do so
                box_thumbnail.alert = True
                box_thumbnail.label(text=f"")
                box_thumbnail.label(
                    text=f"This asset has only {rcount} rating{'' if rcount == 1 else 's'}, please rate."
                )
                # box_thumbnail.label(text=f"Please rate this asset.")

        row = box_thumbnail.row()
        row.alert = False

        row.scale_y = 3
        ui_props = bpy.context.window_manager.blenderkitUI
        if self.asset_data.get("canDownload", True):
            row.prop(
                ui_props,
                "drag_init_button",
                icon="MOUSE_LMB_DRAG",
                text="Click / Drag from here",
                emboss=True,
            )
        else:
            op = layout.operator(
                "wm.blenderkit_url", text="Unlock this asset", icon="UNLOCKED"
            )
            op.url = f'{global_vars.SERVER}/get-blenderkit/{self.asset_data["id"]}/?from_addon=True'

    def draw_menu_desc_author(self, context, layout, width=330):
        box = layout.column()

        box.emboss = "NORMAL"
        # left - tooltip & params
        row = box.row()
        split_factor = 0.7
        split_left = row.split(factor=split_factor)
        col = split_left.column()
        width_left = int(width * split_factor)
        self.draw_description(col, width=width_left)

        self.draw_properties(col, width=width_left)

        # right - menu
        split_right = split_left.split()
        col = split_right.column()
        self.draw_menu(context, col)

        # author
        self.draw_author_area(context, box, width=width)

        # self.draw_author_area(context, box, width=width)
        #
        # col = box.column_flow(columns=2)
        # self.draw_menu(context, col)
        #
        #
        # # self.draw_description(box, width=int(width))
        # self.draw_properties(box, width=int(width))

        # define enum flags

    def draw_titlebar(self, context, layout):
        top_drag_bar = layout.box()
        bcats = global_vars.DATA["bkit_categories"]

        cat_path = categories.get_category_path(bcats, self.asset_data["category"])[1:]

        cat_path_names = categories.get_category_name_path(
            bcats, self.asset_data["category"]
        )[1:]

        aname = self.asset_data["displayName"]
        aname = aname[0].upper() + aname[1:]

        name_row = top_drag_bar.row()

        pcoll = icons.icon_collections["main"]

        name_row.label(text="", icon_value=pcoll["logo"].icon_id)

        for i, c in enumerate(cat_path):
            cat_name = cat_path_names[i]
            ui_props = bpy.context.window_manager.blenderkitUI
            if i < len(cat_path) - 1:
                bl_id = "view3d.blenderkit_set_category_in_popup_card"
            else:
                bl_id = "view3d.blenderkit_set_category_in_popup_card_last"
            op = name_row.operator(bl_id, text=cat_name + "     >", emboss=True)
            op.asset_type = ui_props.asset_type
            # this gets filled not to change anything in browsing categories
            op.category_browse = global_vars.DATA["active_category_browse"][
                ui_props.asset_type
            ][-1]
            # but enables to direclty browse the category clicked.
            op.category_search = c
            # name_row.label(text='>')

        name_row.label(text=aname)
        push_op_left(name_row, strength=3)
        op = name_row.operator("view3d.close_popup_button", text="", icon="CANCEL")

    def draw_comment_response(self, context, layout, comment_id):
        if not utils.user_logged_in():
            return
        pcoll = icons.icon_collections["main"]

        layout.separator()

        row = layout.row()
        ui_props = bpy.context.window_manager.blenderkitUI
        split = row.split(factor=0.8, align=True)
        split.active = True
        split.prop(ui_props, "new_comment", text="", icon="GREASEPENCIL")
        split = split.split()
        op = split.operator(
            "wm.blenderkit_post_comment",
            text="post comment",
            icon_value=pcoll["post_comment"].icon_id,
        )
        op.asset_id = self.asset_data["assetBaseId"]
        op.comment_id = comment_id

        layout.separator()

    def draw_comment(
        self, context: Context, layout: UILayout, comment: dict, width: int = 330
    ):
        row = layout.row()
        if comment["level"] > 0:
            split = row.split(factor=0.05 * comment["level"])
            split.label(text="")
            row = split.split()
        box = row.box()
        box.emboss = "NORMAL"
        row = box.row()
        factor = 0.8
        if comment["canChangeIsPrivate"]:
            factor = 0.7
        split = row.split(factor=factor)
        is_moderator = comment["userModerator"]
        if is_moderator:
            role_text = f" - moderator"
        else:
            role_text = ""
        row = split.row()
        row.enabled = False
        row.label(text=f"{comment['submitDate']} - {comment['userName']}{role_text}")

        if comment["canChangeIsPrivate"]:
            if comment["isPrivate"]:
                ptext = "Private"
                val = False
            else:
                ptext = "Public"
                val = True
            split = split.split()
            split = split.split(factor=0.333)
            split.enabled = True
            op = split.operator(
                "wm.blenderkit_is_private_comment", text=ptext
            )  # , icon='TRIA_DOWN')
            op.asset_id = self.asset_data["assetBaseId"]  # type: ignore
            op.comment_id = comment["id"]  # type: ignore
            op.is_private = val  # type: ignore

        removal = False
        likes = 0
        dislikes = 0
        user_liked = False
        user_disliked = False
        profile = global_vars.BKIT_PROFILE

        for l in comment["flags"]:
            if l["flag"] == "like":
                likes += 1
                if profile is not None:
                    if l["id"] == profile.id:
                        user_liked = True
            if l["flag"] == "dislike":
                dislikes += 1
                if profile is not None:
                    if l["id"] == profile.id:
                        user_disliked = True

            if l["flag"] == "removal":
                removal = True

        # row = box.row()
        split = split.split()
        split_like = split.split(factor=0.5)
        sub_like = split_like.row()
        sub_like.enabled = utils.user_logged_in() and not user_liked
        # split1.emboss = 'NONE'
        op = sub_like.operator(
            "wm.blenderkit_upvote_comment", text=str(likes), icon="TRIA_UP"
        )
        op.asset_id = self.asset_data["assetBaseId"]  # type: ignore
        op.comment_id = comment["id"]  # type: ignore
        op.flag = "like"  # type: ignore

        split_dislike = split_like.split()
        split_dislike = split_dislike.row()
        split_dislike.enabled = utils.user_logged_in() and not user_disliked
        op = split_dislike.operator(
            "wm.blenderkit_upvote_comment", text=str(dislikes), icon="TRIA_DOWN"
        )
        op.asset_id = self.asset_data["assetBaseId"]  # type: ignore
        op.comment_id = comment["id"]  # type: ignore
        op.flag = "dislike"  # type: ignore

        if removal:
            row.alert = True
            row.label(text="", icon="ERROR")
        rows = utils.label_multiline(
            box,
            text=comment["comment"],
            width=width * (1 - 0.05 * comment["level"]),
            use_urls=True,
        )

        if utils.profile_is_validator():
            row = box.row()
            split = row.split(factor=0.95)
            split.label(text="")
            split = split.split()
            row.alert = False
            op = row.operator("wm.url_open", text="", icon="GREASEPENCIL")
            op.url = f'{global_vars.SERVER}/bksecretadmin/django_comments_xtd/xtdcomment/{comment["id"]}/change/'  # type: ignore
            # row.alert = True
            # op = row.operator("wm.url_open", text="", icon='CANCEL')
            # op.url = f'{global_vars.SERVER}/bksecretadmin/django_comments_xtd/xtdcomment/{comment["id"]}/delete/'

        if utils.user_logged_in():
            # row = rows[-1]
            row = layout.row()
            split = row.split(factor=0.8)
            split.label(text="")
            split = split.split()
            op = split.operator(
                "view3d.blenderkit_set_comment_reply_id",
                text="Reply",
                icon="GREASEPENCIL",
            )
            op.comment_id = comment["id"]  # type: ignore

        # box.label(text=str(comment['flags']))

    def draw(self, context):
        layout = self.layout
        # top draggable bar with name of the asset
        top_row = layout.row()
        self.draw_titlebar(context, top_row)
        # left side
        row = layout.row(align=True)
        split_ratio = 0.45
        split_left = row.split(factor=split_ratio)
        left_column = split_left.column()
        self.draw_thumbnail_box(left_column, width=int(self.width * split_ratio))
        if not utils.user_is_owner(asset_data=self.asset_data):
            # Draw ratings, but not for owners of assets - doesn't make sense.
            ratings_box = left_column.box()
            self.prefill_ratings()
            ratings.draw_ratings_menu(self, context, ratings_box)
        # self.draw_description(left_column, width = int(self.width*split_ratio))
        # right split
        split_right = split_left.split()
        self.draw_menu_desc_author(
            context, split_right, width=int(self.width * (1 - split_ratio))
        )

        # else:
        #     ratings_box.label('Here you should find ratings, but you can not rate your own assets ;)')

        tip_box = layout.box()
        tip_box.label(text=self.tip)
        # comments
        ui_props = bpy.context.window_manager.blenderkitUI
        if ui_props.reply_id == 0:
            self.draw_comment_response(context, layout, 0)
        comments = global_vars.DATA.get("asset comments", {})
        self.comments = comments.get(self.asset_data["assetBaseId"], [])
        if self.comments is not None:
            for comment in self.comments:
                self.draw_comment(context, layout, comment, width=self.width)
                if ui_props.reply_id == comment["id"]:
                    self.draw_comment_response(context, layout, comment["id"])

    def execute(self, context):
        wm = context.window_manager
        ui_props = context.window_manager.blenderkitUI
        ui_props.draw_tooltip = False
        ui_props.reply_id = 0

        sr = global_vars.DATA["search results"]
        asset_data = sr[ui_props.active_index]
        self.asset_data = asset_data

        self.img = ui.get_large_thumbnail_image(asset_data)
        utils.img_to_preview(self.img, copy_original=True)

        self.asset_type = asset_data["assetType"]
        self.asset_id = asset_data["id"]
        # self.tex = utils.get_hidden_texture(self.img)
        # self.tex.update_tag()

        author_id = int(asset_data["author"]["id"])
        author = global_vars.BKIT_AUTHORS.get(author_id)
        if author and author.gravatarImg and author.gravatarHash:
            self.gimg = utils.get_hidden_image(author.gravatarImg, author.gravatarHash)

        self.tip = f"Tip: {random.choice(global_vars.TIPS)[0]}"

        if utils.user_logged_in():
            ratings_utils.ensure_rating(self.asset_id)
            # pre-fill ratings
            self.prefill_ratings()

        user_preferences = bpy.context.preferences.addons[__package__].preferences
        if (
            user_preferences.asset_popup_counter
            < user_preferences.asset_popup_counter_max
        ):
            user_preferences.asset_popup_counter += 1
        # get comments
        api_key = user_preferences.api_key
        comments = comments_utils.get_comments_local(asset_data["assetBaseId"])
        # if comments is None:
        client_lib.get_comments(asset_data["assetBaseId"], api_key)

        # TODO: SHOULD BE DONE ONCE COMMENTS TASK IS RETURNED - HOW TO INVOKE REFRESH FROM HANDLE_GET_COMMENTS_TASK
        comments = global_vars.DATA.get("asset comments", {})
        self.comments = comments.get(asset_data["assetBaseId"], [])

        return wm.invoke_popup(self, width=self.width)


class OBJECT_MT_blenderkit_login_menu(bpy.types.Menu):
    bl_label = "BlenderKit login/signup:"
    bl_idname = "OBJECT_MT_blenderkit_login_menu"

    def draw(self, context):
        layout = self.layout

        # utils.label_multiline(layout, text=message)
        draw_login_buttons(layout)


class SetCommentReplyId(bpy.types.Operator):
    """Set comment reply ID, setting to which comment it is replied to and where the input box should be shown."""

    bl_idname = "view3d.blenderkit_set_comment_reply_id"
    bl_label = "BlenderKit Set Comment reply ID"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    comment_id: bpy.props.IntProperty(  # type: ignore[valid-type]
        name="Category", description="set this category active", default=0
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        ui_props = bpy.context.window_manager.blenderkitUI
        ui_props.reply_id = self.comment_id
        # print(f'changed reply id to {self.comment_id}')
        return {"FINISHED"}


class SetCategoryOperatorOrigin(bpy.types.Operator):
    bl_idname = "view3d.blenderkit_set_category_origin"
    bl_label = "BlenderKit Set Active Category"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    category_browse: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Category browse",
        description="set this category active for browsing",
        default="",
    )
    category_search: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Category search",
        description="set this category active for search",
        default="",
    )

    asset_type: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset Type", description="asset type", default="MODEL"
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        acat = global_vars.DATA["active_category_browse"][self.asset_type]
        if self.category_browse == "":
            acat.remove(acat[-1])
        elif self.category_browse == acat[-1]:
            # don't change category if it is the same
            pass
        else:
            acat.append(self.category_browse)
        search_props = utils.get_search_props()
        search_props.search_category = self.category_search
        # we have to write back to wm. Thought this should happen with original list.
        global_vars.DATA["active_category_browse"][self.asset_type] = acat
        return {"FINISHED"}


# TODO: Handle here SelectSubcategory/SelectCategory
# and VisitSubcategory/VisitCategory and VisitUpperCategory/VisitUpperSubcategory
class SetCategoryOperator(SetCategoryOperatorOrigin):
    """Visit subcategory"""

    bl_idname = "view3d.blenderkit_set_category"


class SetCategoryOperatorInPopupCard(SetCategoryOperatorOrigin):
    """Subcategory of the asset. Click to search this subcategory."""

    bl_idname = "view3d.blenderkit_set_category_in_popup_card"


class SetCategoryOperatorLastInPopupCard(SetCategoryOperatorOrigin):
    """Subcategory of the asset. Click to search this subcategory. Shortcut: Hover over asset in the asset bar and press 'C'."""

    bl_idname = "view3d.blenderkit_set_category_in_popup_card_last"


class ClosePopupButton(bpy.types.Operator):
    """Close popup window"""

    bl_idname = "view3d.close_popup_button"
    bl_label = "Close popup"
    bl_options = {"REGISTER", "INTERNAL"}

    @classmethod
    def poll(cls, context):
        return True

    def win_close(self):
        VK_ESCAPE = 0x1B
        ctypes.windll.user32.keybd_event(VK_ESCAPE)
        return True

    def mouse_trick(self, context, x, y):
        # import time
        context.area.tag_redraw()
        w = context.window
        w.cursor_warp(w.x + 15, w.y + w.height - 15)
        # time.sleep(.12)
        w.cursor_warp(x, y)
        context.area.tag_redraw()

    def invoke(self, context, event):
        if platform.system() == "Windows":
            self.win_close()
        else:
            self.mouse_trick(context, event.mouse_x, event.mouse_y)
        return {"FINISHED"}


class PopupDialog(bpy.types.Operator):
    """Small popup dialog to inform user."""

    bl_idname = "wm.blenderkit_popup_dialog"
    bl_label = "BlenderKit message:"
    bl_options = {"REGISTER", "INTERNAL"}

    message: bpy.props.StringProperty(default="")  # type: ignore[valid-type]
    width: bpy.props.IntProperty(default=300)  # type: ignore[valid-type]

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.label(text=self.message)
        row.operator("view3d.close_popup_button", text="", icon="CANCEL")
        layout.active_default = True

    def execute(self, context):
        wm = bpy.context.window_manager
        return wm.invoke_popup(self, width=self.width)


class UrlPopupDialog(bpy.types.Operator):
    """Generate Cycles thumbnail for model assets"""

    bl_idname = "wm.blenderkit_url_dialog"
    bl_label = "BlenderKit message:"
    bl_options = {"REGISTER", "INTERNAL"}

    url: bpy.props.StringProperty(name="Url", description="url", default="")  # type: ignore[valid-type]

    link_text: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Url", description="url", default="Go to website"
    )

    message: bpy.props.StringProperty(name="Text", description="text", default="")  # type: ignore[valid-type]

    # @classmethod
    # def poll(cls, context):
    #     return bpy.context.view_layer.objects.active is not None

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.label(text=self.message)
        row.operator("view3d.close_popup_button", text="", icon="CANCEL")

        layout.active_default = True
        op = layout.operator("wm.url_open", text=self.link_text, icon="QUESTION")
        if not utils.user_logged_in():
            utils.label_multiline(
                layout,
                text="Already subscribed? You need to login to access your Full Plan.",
                width=300,
            )

            layout.operator_context = "EXEC_DEFAULT"
            layout.operator("wm.blenderkit_login", text="Login", icon="URL").signup = (
                False
            )
        op.url = self.url

    def execute(self, context):
        wm = bpy.context.window_manager
        return wm.invoke_popup(self, width=300)


class LoginPopupDialog(bpy.types.Operator):
    """Popup a dialog which enables the user to log in after being logged out automatically."""

    bl_idname = "wm.blenderkit_login_dialog"
    bl_label = "BlenderKit login"
    bl_options = {"REGISTER", "INTERNAL"}

    message: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Message",
        description="",
        default="Your were logged out from . Please login again. ",
    )

    link_text: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Url", description="url", default="Login to BlenderKit"
    )

    # @classmethod
    # def poll(cls, context):
    #     return bpy.context.view_layer.objects.active is not None

    def draw(self, context):
        layout = self.layout
        utils.label_multiline(layout, text=self.message, width=300)

        layout.active_default = True
        layout.operator_context = "EXEC_DEFAULT"
        layout.operator(
            "wm.blenderkit_login", text=self.link_text, icon="URL"
        ).signup = False

    def execute(self, context):
        return {"FINISHED"}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=300)


def draw_panel_categories(layout, context):
    ui_props = bpy.context.window_manager.blenderkitUI
    user_preferences = bpy.context.preferences.addons[__package__].preferences

    search_props = utils.get_search_props()
    acat_search = search_props.search_category
    # row = layout.row()
    # row.prop(ui_props, 'asset_type', expand=True, icon_only=True)
    if global_vars.DATA.get("bkit_categories") == None:
        return
    col = layout.column(align=True)
    if global_vars.DATA.get("active_category_browse") is not None:
        acat = global_vars.DATA["active_category_browse"][ui_props.asset_type]
        if len(acat) > 1:
            # we are in subcategory, so draw the parent button
            op = col.operator(
                "view3d.blenderkit_set_category",
                text="...",
                icon="FILE_PARENT",
            )
            op.asset_type = ui_props.asset_type
            op.category_browse = ""
            op.category_search = acat[-2]
        elif acat_search not in ("", ui_props.asset_type.lower()):
            # we are in subcategory, so draw the parent button
            op = col.operator(
                "view3d.blenderkit_set_category",
                text="[All]",
                icon="FILE_PARENT",
            )
            op.asset_type = ui_props.asset_type
            op.category_browse = acat[-1]
            op.category_search = acat[-1]

    cats = categories.get_category(global_vars.DATA["bkit_categories"], cat_path=acat)
    # draw freebies only in models parent category
    # if ui_props.asset_type == 'MODEL' and len(acat) == 1:
    #     op = col.operator('view3d.blenderkit_asset_bar_widget', text='freebies')
    #     op.free_only = True

    for c in cats["children"]:
        if c["assetCount"] > 0 or (
            utils.profile_is_validator() and user_preferences.categories_fix
        ):
            row = col.row(align=True)
            if (
                len(c["children"]) > 0
                and c["assetCount"] > 15
                or (utils.profile_is_validator() and user_preferences.categories_fix)
            ):
                row = row.split(factor=0.8, align=True)
            # row = split.split()
            ctext = "%s (%i)" % (c["name"], c["assetCount"])

            emboss = acat_search == c["slug"]
            op = row.operator(
                "view3d.blenderkit_set_category", text=ctext, depress=emboss
            )
            op.asset_type = ui_props.asset_type
            op.category_browse = acat[-1]
            op.category_search = c["slug"]

            if (
                len(c["children"]) > 0
                and c["assetCount"] > 15
                or (utils.profile_is_validator() and user_preferences.categories_fix)
            ):
                # row = row.split()
                op = row.operator("view3d.blenderkit_set_category", text=">>")
                op.asset_type = ui_props.asset_type
                op.category_browse = c["slug"]
                op.category_search = c["slug"]

                # for c1 in c['children']:
                #     if c1['assetCount']>0:
                #         row = col.row()
                #         split = row.split(percentage=.2)
                #         row = split.split()
                #         row = split.split()
                #         ctext = '%s (%i)' % (c1['name'], c1['assetCount'])
                #         op = row.operator('view3d.blenderkit_search', text=ctext)
                #         op.category = c1['slug']


class VIEW3D_PT_blenderkit_downloads(Panel):
    bl_category = "BlenderKit"
    bl_idname = "VIEW3D_PT_blenderkit_downloads"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Downloads"

    @classmethod
    def poll(cls, context):
        return len(download.download_tasks) > 0

    def draw(self, context):
        layout = self.layout
        for key, data in download.download_tasks.items():
            row = layout.row()
            row.label(text=data["asset_data"]["name"])
            row.label(text=str(int(data["progress"])) + " %")
            op = row.operator("scene.blenderkit_download_kill", text="", icon="CANCEL")
            op.task_id = key
            if data.get("retry_counter", 0) > 0:
                row = layout.row()
                row.label(text="failed. retrying ... ", icon="ERROR")
                row.label(text=str(data["retry_counter"]))

                layout.separator()


def update_header_menu_fold(self, context):
    preferences = bpy.context.preferences.addons[__package__].preferences
    if preferences.header_menu_fold and asset_bar_op.asset_bar_operator is not None:
        bpy.ops.view3d.run_assetbar_fix_context(keep_running=False, do_search=False)
    elif not preferences.header_menu_fold and asset_bar_op.asset_bar_operator is None:
        bpy.ops.view3d.run_assetbar_fix_context(keep_running=True, do_search=False)


def header_search_draw(self, context):
    """Top bar menu in 3D view"""
    if not utils.guard_from_crash():
        return

    preferences = bpy.context.preferences.addons[__package__].preferences
    if not preferences.search_in_header:
        return
    if context.mode not in ("PAINT_TEXTURE", "OBJECT", "SCULPT", "POSE"):
        return
    # hide search bar if overlays are hidden
    # this was nice, but was then reported as a bug by some users, who didn't understand this behaviour.
    # users tend to work also with overlays hidden, so this was not a good idea.
    # if context.area.spaces[0].overlay.show_overlays == False:
    #     return

    layout = self.layout
    wm = bpy.context.window_manager
    ui_props = bpy.context.window_manager.blenderkitUI

    props_dict = {
        "MODEL": wm.blenderkit_models,
        "MATERIAL": wm.blenderkit_mat,
        "BRUSH": wm.blenderkit_brush,
        "HDR": wm.blenderkit_HDR,
        "SCENE": wm.blenderkit_scene,
        "NODEGROUP": wm.blenderkit_nodegroup,
    }
    props = props_dict[ui_props.asset_type]
    icons_dict = {
        "MODEL": "OBJECT_DATAMODE",
        "MATERIAL": "MATERIAL",
        "BRUSH": "BRUSH_DATA",
        "HDR": "WORLD",
        "SCENE": "SCENE_DATA",
        "NODEGROUP": "NODETREE",
    }

    asset_type_icon = icons_dict[ui_props.asset_type]
    pcoll = icons.icon_collections["main"]

    # the center snap menu is in edit and object mode if tool settings are off.
    # if context.space_data.show_region_tool_header == True or context.mode[:4] not in ('EDIT', 'OBJE'):
    # layout.separator_spacer()
    row = layout.row(align=True)
    row.scale_x = 0.9

    if preferences.header_menu_fold:
        row.prop(
            preferences, "header_menu_fold", text="", icon="RIGHTARROW", emboss=False
        )
        row.prop(
            preferences,
            "header_menu_fold",
            text="",
            icon_value=pcoll[ui_props.logo_status].icon_id,
            emboss=False,
        )
        return
    else:
        row.prop(
            preferences, "header_menu_fold", text="", icon="DOWNARROW_HLT", emboss=False
        )

    # draw logo as part of the folding UI, it is better clickable.
    row.prop(
        preferences,
        "header_menu_fold",
        text="",
        icon_value=pcoll[ui_props.logo_status].icon_id,
        emboss=False,
    )
    # row.label(text="", icon_value=pcoll[ui_props.logo_status].icon_id)

    layout = layout.row(align=True)
    # layout.separator()
    if not global_vars.CLIENT_RUNNING:
        layout.label(text="Waiting for Client")
        return

    layout.prop(
        ui_props,
        "asset_type",
        expand=True,
        icon_only=True,
        text="",
        icon=asset_type_icon,
    )

    row = layout.row()
    if (context.region.width) > 700:
        row.ui_units_x = 5 + int(context.region.width / 200)
    search_field_width = bpy.context.preferences.addons[
        __package__
    ].preferences.search_field_width
    if search_field_width > 0:
        row.ui_units_x = search_field_width

    row.prop(props, "search_keywords", text="", icon="VIEWZOOM")

    draw_assetbar_show_hide(layout, props)
    layout.prop(ui_props, "search_bookmarks", text="", icon="BOOKMARKS")
    if (
        props.search_category == ui_props.asset_type.lower()
        or props.search_category == ""
    ):
        icon_id = pcoll["categories"].icon_id
    else:
        icon_id = pcoll["categories_active"].icon_id

    layout.popover(
        panel="VIEW3D_PT_blenderkit_categories",
        text="",
        icon_value=icon_id,
    )

    # FILTER ICON
    if props.use_filters:
        icon_id = pcoll["filter_active"].icon_id
    else:
        icon_id = pcoll["filter"].icon_id

    if context.mode == "EDIT_MESH":
        # geo node tools right now.
        pass

    elif ui_props.asset_type == "MODEL":
        layout.popover(
            panel="VIEW3D_PT_blenderkit_advanced_model_search",
            text="",
            icon_value=icon_id,
        )

    elif ui_props.asset_type == "MATERIAL":
        layout.popover(
            panel="VIEW3D_PT_blenderkit_advanced_material_search",
            text="",
            icon_value=icon_id,
        )
    elif ui_props.asset_type == "SCENE":
        layout.popover(
            panel="VIEW3D_PT_blenderkit_advanced_scene_search",
            text="",
            icon_value=icon_id,
        )
    elif ui_props.asset_type == "HDR":
        layout.popover(
            panel="VIEW3D_PT_blenderkit_advanced_HDR_search",
            text="",
            icon_value=icon_id,
        )
    elif ui_props.asset_type == "BRUSH":
        layout.popover(
            panel="VIEW3D_PT_blenderkit_advanced_brush_search",
            text="",
            icon_value=icon_id,
        )

    # NSFW filter shield badge - only for models right now
    if preferences.nsfw_filter and ui_props.asset_type == "MODEL":
        layout.prop(
            preferences,
            "nsfw_filter",
            text="",
            icon_value=pcoll["nsfw"].icon_id,
            emboss=False,
        )

    # elif ui_props.asset_type in ('BRUSH', 'SCENE'):
    #     # this is just a placeholder so that the UI doesn't get out of alignment
    #     row = layout.column()
    #     row.enabled = False
    #     row.ui_units_x = 1.5
    #     row.label(text='', icon_value=icon_id)

    notifications = global_vars.DATA.get("bkit notifications")
    if notifications is not None and notifications.get("count", 0) > 0:
        layout.operator(
            "wm.show_notifications", text="", icon_value=pcoll["bell"].icon_id
        )
        # layout.popover(panel="VIEW3D_PT_blenderkit_notifications", text="", icon_value=pcoll['bell'].icon_id)

    if utils.profile_is_validator():
        search_props = utils.get_search_props()
        layout.prop(search_props, "search_verification_status", text="")


def ui_message(title, message):
    def draw_message(self, context):
        layout = self.layout
        utils.label_multiline(layout, text=message, width=400)

    bpy.context.window_manager.popup_menu(draw_message, title=title, icon="INFO")


classes = (
    SetCategoryOperatorOrigin,
    SetCategoryOperator,
    SetCategoryOperatorInPopupCard,
    SetCategoryOperatorLastInPopupCard,
    SetCommentReplyId,
    VIEW3D_PT_blenderkit_profile,
    # VIEW3D_PT_blenderkit_login,
    # VIEW3D_PT_blenderkit_notifications,
    VIEW3D_PT_blenderkit_unified,
    VIEW3D_PT_blenderkit_advanced_model_search,
    VIEW3D_PT_blenderkit_advanced_material_search,
    VIEW3D_PT_blenderkit_advanced_scene_search,
    VIEW3D_PT_blenderkit_advanced_HDR_search,
    VIEW3D_PT_blenderkit_advanced_brush_search,
    VIEW3D_PT_blenderkit_categories,
    VIEW3D_PT_blenderkit_import_settings,
    VIEW3D_PT_blenderkit_model_properties,
    VIEW3D_MT_blenderkit_model_properties,
    NODE_PT_blenderkit_material_properties,
    OpenBlenderKitDiscord,
    OpenSystemDirectory,
    OpenAssetDirectory,
    OpenAddonDirectory,
    OpenGlobalDirectory,
    OpenClientLog,
    OpenTempDirectory,
    # VIEW3D_PT_blenderkit_ratings,
    VIEW3D_PT_blenderkit_downloads,
    # OBJECT_MT_blenderkit_resolution_menu,
    OBJECT_MT_blenderkit_asset_menu,
    OBJECT_MT_blenderkit_login_menu,
    AssetPopupCard,
    PopupDialog,
    UrlPopupDialog,
    ClosePopupButton,
    BlenderKitWelcomeOperator,
    MarkNotificationRead,
    UpvoteComment,
    SetPrivateComment,
    PostComment,
    # DeleteComment,
    ShowNotifications,
    LogoStatus,
    NotificationOpenTarget,
    MarkAllNotificationsRead,
    LoginPopupDialog,
)


def header_search_draw_tools(self, context):
    if not bpy.context.area.spaces.active.show_region_tool_header:
        return
    if bpy.context.mode in ("SCULPT", "PAINT_TEXTURE"):
        return
    header_search_draw(self, context)


def header_search_draw_others(self, context):
    if (
        not bpy.context.area.spaces.active.show_region_tool_header
        or bpy.context.mode in ("SCULPT", "PAINT_TEXTURE")
    ):
        header_search_draw(self, context)


def header_draw(self, context):
    layout = self.layout

    self.draw_tool_settings(context)

    layout.separator_spacer()
    header_search_draw_tools(self, context)
    layout.separator_spacer()

    self.draw_mode_settings(context)


def object_context_draw(self, context):
    preferences = bpy.context.preferences.addons[__package__].preferences
    layout = self.layout
    pcoll = icons.icon_collections["main"]
    if not preferences.show_VIEW3D_MT_blenderkit_model_properties:
        return
    layout.menu(
        VIEW3D_MT_blenderkit_model_properties.bl_idname,
        icon_value=pcoll["logo"].icon_id,
    )


def register_ui_panels():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.VIEW3D_HT_tool_header.draw = header_draw
    # bpy.types.VIEW3D_HT_tool_header.append(header_search_draw)
    bpy.types.VIEW3D_MT_editor_menus.append(header_search_draw_others)
    bpy.types.VIEW3D_MT_object_context_menu.append(object_context_draw)
    # bpy.types.VIEW3D_PT_tools_active.prepend(header_search_draw_new)


def unregister_ui_panels():
    # bpy.types.VIEW3D_HT_tool_header.remove(header_search_draw)
    bpy.types.VIEW3D_MT_editor_menus.remove(header_search_draw_others)
    bpy.types.VIEW3D_MT_object_context_menu.remove(object_context_draw)
    # bpy.types.VIEW3D_PT_tools_active.remove(header_search_draw_new)
    for c in classes:
        # print('unregister', c)
        bpy.utils.unregister_class(c)
