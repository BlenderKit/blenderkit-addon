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


import json
import logging
import os
import re
import tempfile
from pathlib import Path

import bpy
from bpy.props import (  # TODO only keep the ones actually used when cleaning
    BoolProperty,
    EnumProperty,
    StringProperty,
)
from bpy.types import Operator

from . import (
    asset_bar_op,
    asset_inspector,
    autothumb,
    categories,
    daemon_lib,
    global_vars,
    image_utils,
    overrides,
    paths,
    reports,
    ui_panels,
    utils,
    version_checker,
)
from .daemon import daemon_tasks


NAME_MINIMUM = 3
NAME_MAXIMUM = 40
TAGS_MINIMUM = 3
DESCRIPTION_MINIMUM = 20

BLENDERKIT_EXPORT_DATA_FILE = "data.json"
bk_logger = logging.getLogger(__name__)
licenses = (
    ("royalty_free", "Royalty Free", "royalty free commercial license"),
    ("cc_zero", "Creative Commons Zero", "Creative Commons Zero"),
)


def add_version(data):
    data["sourceAppName"] = "blender"
    data["sourceAppVersion"] = version_checker.get_blender_version()
    data["addonVersion"] = version_checker.get_addon_version()


def write_to_report(props, text):
    props.report = props.report + " - " + text + "\n\n"


def check_missing_data_model(props):
    autothumb.update_upload_model_preview(None, None)
    if props.engine == "NONE":
        write_to_report(props, "Set at least one rendering/output engine")

    # if not any(props.dimensions):
    #     write_to_report(props, 'Run autotags operator or fill in dimensions manually')


def check_missing_data_scene(props):
    autothumb.update_upload_model_preview(None, None)
    if props.engine == "NONE":
        write_to_report(props, "Set at least one rendering/output engine")


def check_missing_data_material(props):
    autothumb.update_upload_material_preview(None, None)
    if props.engine == "NONE":
        write_to_report(props, "Set rendering/output engine")


def check_missing_data_brush(props):
    autothumb.update_upload_brush_preview(None, None)


def check_missing_data(asset_type, props, upload_thumbnail=True):
    """
    Check if user did everything alright for particular assets and notify her back if not.
    Parameters
    ----------
    asset_type
    props

    Returns
    -------

    """
    props.report = ""
    if len(props.name) < NAME_MINIMUM:
        write_to_report(
            props,
            "The asset name provided is too short.\n"
            f"   Please ensure your asset name is at least {NAME_MINIMUM} characters long.",
        )
    if len(props.name) > NAME_MAXIMUM:
        write_to_report(
            props,
            "The asset name provided exceeds the character limit.\n"
            f"   Please ensure your asset name is no more than {NAME_MAXIMUM} characters long.",
        )

    if props.is_private == "PUBLIC":
        category_ok = props.category == "NONE"
        subcategory_ok = props.subcategory != "EMPTY" and props.subcategory == "NONE"
        subcategory1_ok = props.subcategory1 != "EMPTY" and props.subcategory1 == "NONE"
        if category_ok or subcategory_ok or subcategory1_ok:
            write_to_report(
                props,
                "Category, subcategory, or sub-subcategory has not been selected.\n"
                "   Please ensure you select appropriate values; 'None' is not a valid selection.\n"
                "   Proper categorization significantly improves your asset's discoverability.",
            )

    if upload_thumbnail:
        if asset_type in ("MODEL", "SCENE", "MATERIAL"):
            thumb_path = bpy.path.abspath(props.thumbnail)
            if props.thumbnail == "":
                write_to_report(
                    props,
                    "A thumbnail image has not been provided.\n"
                    "   Please add a thumbnail in JPG or PNG format, ensuring at least 1024x1024 pixels.",
                )
            elif not os.path.exists(Path(thumb_path)):
                write_to_report(
                    props,
                    "Thumbnail filepath does not exist on the disk.\n"
                    "   Please check the filepath and try again.",
                )

        if asset_type == "BRUSH":
            brush = utils.get_active_brush()
            if brush is not None:
                thumb_path = bpy.path.abspath(brush.icon_filepath)
                if thumb_path == "":
                    write_to_report(
                        props,
                        "Brush Icon Filepath has not been provided.\n"
                        "   Please check Custom Icon option add a Brush Icon in JPG or PNG format, ensuring at least 1024x1024 pixels.",
                    )
                elif not os.path.exists(Path(thumb_path)):
                    write_to_report(
                        props,
                        "Brush Icon Filepath does not exist on the disk.\n"
                        "   Please check the filepath and try again.",
                    )

    if props.is_private == "PUBLIC":
        check_public_requirements(props)

    if asset_type == "MODEL":
        check_missing_data_model(props)
    elif asset_type == "SCENE":
        check_missing_data_scene(props)
    elif asset_type == "MATERIAL":
        check_missing_data_material(props)
    elif asset_type == "BRUSH":
        check_missing_data_brush(props)

    if props.report != "":
        props.report = (
            f"Before {props.is_private.lower()} upload, please fix:\n\n" + props.report
        )


def check_public_requirements(props: str):
    """Check requirements for public upload. Add error message into props.report if needed."""
    if props.description == "":
        write_to_report(
            props,
            "No asset description has been provided.\n"
            f"   Please write a description of at least {DESCRIPTION_MINIMUM} characters.\n"
            "   A comprehensive description enhances your asset's visibility\n"
            "   in relevant search results.",
        )
    elif len(props.description) < DESCRIPTION_MINIMUM:
        write_to_report(
            props,
            "The asset description provided is too brief.\n"
            f"   Please ensure your description is at least {DESCRIPTION_MINIMUM} characters long.\n"
            "   A comprehensive description enhances your asset's visibility\n"
            "   in relevant search results.",
        )

    if props.tags == "":
        write_to_report(
            props,
            "No tags have been provided for your asset.\n"
            f"   Please add at least {TAGS_MINIMUM} tags to improve its discoverability.\n"
            "   Tags enhance your asset's visibility in relevant search results.",
        )
    elif len(props.tags.split(",")) < TAGS_MINIMUM:
        write_to_report(
            props,
            "Not enough tags have been provided for your asset.\n"
            f"   Please ensure you have at least {TAGS_MINIMUM} tags to improve its discoverability.\n"
            "   Tags enhance your asset's visibility in relevant search results.",
        )


def sub_to_camel(content):
    replaced = re.sub(r"_.", lambda m: m.group(0)[1].upper(), content)
    return replaced


def get_upload_data(caller=None, context=None, asset_type=None):
    """
    works though metadata from addom props and prepares it for upload to dicts.
    Parameters
    ----------
    caller - upload operator or none
    context - context
    asset_type - asset type in capitals (blender enum)

    Returns
    -------
    export_ddta- all extra data that the process needs to upload and communicate with UI from a thread.
        - eval_path_computing - string path to UI prop that denots if upload is still running
        - eval_path_state - string path to UI prop that delivers messages about upload to ui
        - eval_path - path to object holding upload data to be able to access it with various further commands
        - models - in case of model upload, list of objects
        - thumbnail_path - path to thumbnail file

    upload_data - asset_data generated from the ui properties

    """
    user_preferences = bpy.context.preferences.addons["blenderkit"].preferences
    export_data = {
        # "type": asset_type,
    }
    upload_params = {}
    if asset_type == "MODEL":
        # Prepare to save the file
        mainmodel = utils.get_active_model()

        props = mainmodel.blenderkit

        obs = utils.get_hierarchy(mainmodel)
        obnames = []
        for ob in obs:
            obnames.append(ob.name)
        export_data["models"] = obnames
        export_data["thumbnail_path"] = bpy.path.abspath(props.thumbnail)

        eval_path_computing = (
            "bpy.data.objects['%s'].blenderkit.uploading" % mainmodel.name
        )
        eval_path_state = (
            "bpy.data.objects['%s'].blenderkit.upload_state" % mainmodel.name
        )
        eval_path = "bpy.data.objects['%s']" % mainmodel.name

        engines = [props.engine.lower()]
        if props.engine1 != "NONE":
            engines.append(props.engine1.lower())
        if props.engine2 != "NONE":
            engines.append(props.engine2.lower())
        if props.engine3 != "NONE":
            engines.append(props.engine3.lower())
        if props.engine == "OTHER":
            engines.append(props.engine_other.lower())

        style = props.style.lower()
        # if style == 'OTHER':
        #     style = props.style_other.lower()

        upload_data = {
            "assetType": "model",
        }
        upload_params = {
            "productionLevel": props.production_level.lower(),
            "model_style": style,
            "engines": engines,
            "modifiers": utils.string2list(props.modifiers),
            "materials": utils.string2list(props.materials),
            "shaders": utils.string2list(props.shaders),
            "uv": props.uv,
            "dimensionX": round(props.dimensions[0], 4),
            "dimensionY": round(props.dimensions[1], 4),
            "dimensionZ": round(props.dimensions[2], 4),
            "boundBoxMinX": round(props.bbox_min[0], 4),
            "boundBoxMinY": round(props.bbox_min[1], 4),
            "boundBoxMinZ": round(props.bbox_min[2], 4),
            "boundBoxMaxX": round(props.bbox_max[0], 4),
            "boundBoxMaxY": round(props.bbox_max[1], 4),
            "boundBoxMaxZ": round(props.bbox_max[2], 4),
            "animated": props.animated,
            "rig": props.rig,
            "simulation": props.simulation,
            "purePbr": props.pbr,
            "faceCount": props.face_count,
            "faceCountRender": props.face_count_render,
            "manifold": props.manifold,
            "objectCount": props.object_count,
            "procedural": props.is_procedural,
            "nodeCount": props.node_count,
            "textureCount": props.texture_count,
            "megapixels": props.total_megapixels,
            # "scene": props.is_scene,
        }
        if props.use_design_year:
            upload_params["designYear"] = props.design_year
        if props.condition != "UNSPECIFIED":
            upload_params["condition"] = props.condition.lower()
        if props.pbr:
            pt = props.pbr_type
            pt = pt.lower()
            upload_params["pbrType"] = pt

        if props.texture_resolution_max > 0:
            upload_params["textureResolutionMax"] = props.texture_resolution_max
            upload_params["textureResolutionMin"] = props.texture_resolution_min
        if props.mesh_poly_type != "OTHER":
            upload_params["meshPolyType"] = (
                props.mesh_poly_type.lower()
            )  # .replace('_',' ')

        optional_params = [
            "manufacturer",
            "designer",
            "design_collection",
            "design_variant",
        ]
        for p in optional_params:
            if eval("props.%s" % p) != "":
                upload_params[sub_to_camel(p)] = eval("props.%s" % p)

    if asset_type == "SCENE":
        # Prepare to save the file
        s = bpy.context.scene

        props = s.blenderkit

        export_data["scene"] = s.name
        export_data["thumbnail_path"] = bpy.path.abspath(props.thumbnail)

        eval_path_computing = "bpy.data.scenes['%s'].blenderkit.uploading" % s.name
        eval_path_state = "bpy.data.scenes['%s'].blenderkit.upload_state" % s.name
        eval_path = "bpy.data.scenes['%s']" % s.name

        engines = [props.engine.lower()]
        if props.engine1 != "NONE":
            engines.append(props.engine1.lower())
        if props.engine2 != "NONE":
            engines.append(props.engine2.lower())
        if props.engine3 != "NONE":
            engines.append(props.engine3.lower())
        if props.engine == "OTHER":
            engines.append(props.engine_other.lower())

        style = props.style.lower()
        # if style == 'OTHER':
        #     style = props.style_other.lower()

        upload_data = {
            "assetType": "scene",
        }
        upload_params = {
            "productionLevel": props.production_level.lower(),
            "model_style": style,
            "engines": engines,
            "modifiers": utils.string2list(props.modifiers),
            "materials": utils.string2list(props.materials),
            "shaders": utils.string2list(props.shaders),
            "uv": props.uv,
            "animated": props.animated,
            # "simulation": props.simulation,
            "purePbr": props.pbr,
            "faceCount": 1,  # props.face_count,
            "faceCountRender": 1,  # props.face_count_render,
            "objectCount": 1,  # props.object_count,
            # "scene": props.is_scene,
        }
        if props.use_design_year:
            upload_params["designYear"] = props.design_year
        if props.condition != "UNSPECIFIED":
            upload_params["condition"] = props.condition.lower()
        if props.pbr:
            pt = props.pbr_type
            pt = pt.lower()
            upload_params["pbrType"] = pt

        if props.texture_resolution_max > 0:
            upload_params["textureResolutionMax"] = props.texture_resolution_max
            upload_params["textureResolutionMin"] = props.texture_resolution_min
        if props.mesh_poly_type != "OTHER":
            upload_params["meshPolyType"] = (
                props.mesh_poly_type.lower()
            )  # .replace('_',' ')

    elif asset_type == "MATERIAL":
        mat = bpy.context.active_object.active_material
        props = mat.blenderkit

        # props.name = mat.name

        export_data["material"] = str(mat.name)
        export_data["thumbnail_path"] = bpy.path.abspath(props.thumbnail)
        # mat analytics happen here, since they don't take up any time...
        asset_inspector.check_material(props, mat)

        eval_path_computing = "bpy.data.materials['%s'].blenderkit.uploading" % mat.name
        eval_path_state = "bpy.data.materials['%s'].blenderkit.upload_state" % mat.name
        eval_path = "bpy.data.materials['%s']" % mat.name

        engine = props.engine
        if engine == "OTHER":
            engine = props.engine_other
        engine = engine.lower()
        style = props.style.lower()
        # if style == 'OTHER':
        #     style = props.style_other.lower()

        upload_data = {
            "assetType": "material",
        }

        upload_params = {
            "material_style": style,
            "engine": engine,
            "shaders": utils.string2list(props.shaders),
            "uv": props.uv,
            "animated": props.animated,
            "purePbr": props.pbr,
            "textureSizeMeters": props.texture_size_meters,
            "procedural": props.is_procedural,
            "nodeCount": props.node_count,
            "textureCount": props.texture_count,
            "megapixels": props.total_megapixels,
        }

        if props.pbr:
            upload_params["pbrType"] = props.pbr_type.lower()

        if props.texture_resolution_max > 0:
            upload_params["textureResolutionMax"] = props.texture_resolution_max
            upload_params["textureResolutionMin"] = props.texture_resolution_min

    elif asset_type == "BRUSH":
        brush = utils.get_active_brush()

        props = brush.blenderkit
        # props.name = brush.name

        export_data["brush"] = str(brush.name)
        export_data["thumbnail_path"] = bpy.path.abspath(brush.icon_filepath)

        eval_path_computing = "bpy.data.brushes['%s'].blenderkit.uploading" % brush.name
        eval_path_state = "bpy.data.brushes['%s'].blenderkit.upload_state" % brush.name
        eval_path = "bpy.data.brushes['%s']" % brush.name

        # mat analytics happen here, since they don't take up any time...

        brush_type = ""
        if bpy.context.sculpt_object is not None:
            brush_type = "sculpt"

        elif bpy.context.image_paint_object:  # could be just else, but for future p
            brush_type = "texture_paint"

        upload_params = {
            "mode": brush_type,
        }

        upload_data = {
            "assetType": "brush",
        }

    elif asset_type == "HDR":
        ui_props = bpy.context.window_manager.blenderkitUI

        # imagename = ui_props.hdr_upload_image
        image = ui_props.hdr_upload_image  # bpy.data.images.get(imagename)
        if not image:
            return None, None

        props = image.blenderkit

        image_utils.analyze_image_is_true_hdr(image)

        # props.name = brush.name
        base, ext = os.path.splitext(image.filepath)
        thumb_path = base + ".jpg"
        export_data["thumbnail_path"] = bpy.path.abspath(thumb_path)

        export_data["hdr"] = str(image.name)
        export_data["hdr_filepath"] = str(bpy.path.abspath(image.filepath))
        # export_data["thumbnail_path"] = bpy.path.abspath(brush.icon_filepath)

        eval_path_computing = "bpy.data.images['%s'].blenderkit.uploading" % image.name
        eval_path_state = "bpy.data.images['%s'].blenderkit.upload_state" % image.name
        eval_path = "bpy.data.images['%s']" % image.name

        # mat analytics happen here, since they don't take up any time...

        upload_params = {
            "textureResolutionMax": props.texture_resolution_max,
            "trueHDR": props.true_hdr,
        }

        upload_data = {
            "assetType": "hdr",
        }

    elif asset_type == "TEXTURE":
        style = props.style
        # if style == 'OTHER':
        #     style = props.style_other

        upload_data = {
            "assetType": "texture",
        }
        upload_params = {
            "style": style,
            "animated": props.animated,
            "purePbr": props.pbr,
            "resolution": props.resolution,
        }
        if props.pbr:
            pt = props.pbr_type
            pt = pt.lower()
            upload_data["pbrType"] = pt

    add_version(upload_data)

    # caller can be upload operator, but also asset bar called from tooltip generator
    if caller and caller.properties.main_file is True:
        upload_data["name"] = props.name
        upload_data["displayName"] = props.name
    else:
        upload_data["displayName"] = props.name

    upload_data["description"] = props.description
    upload_data["tags"] = utils.string2list(props.tags)
    # category is always only one value by a slug, that's why we go down to the lowest level and overwrite.
    if props.category == "" or props.category == "NONE":
        upload_data["category"] = asset_type.lower()
    else:
        upload_data["category"] = props.category
    if props.subcategory not in (
        "NONE",
        "EMPTY",
        "OTHER",
    ):  # if OTHER category is selected, parent category will be used
        upload_data["category"] = props.subcategory
    if props.subcategory1 not in (
        "NONE",
        "EMPTY",
        "OTHER",
    ):  # if OTHER category is selected, parent category will be used
        upload_data["category"] = props.subcategory1

    upload_data["license"] = props.license
    upload_data["isFree"] = props.is_free == "FREE"
    upload_data["isPrivate"] = props.is_private == "PRIVATE"
    upload_data["token"] = user_preferences.api_key

    upload_data["parameters"] = upload_params

    # if props.asset_base_id != '':
    export_data["assetBaseId"] = props.asset_base_id
    export_data["id"] = props.id
    export_data["eval_path_computing"] = eval_path_computing
    export_data["eval_path_state"] = eval_path_state
    export_data["eval_path"] = eval_path

    return export_data, upload_data


def update_free_full(self, context):
    if self.asset_type == "material":
        if self.free_full == "FULL":
            self.free_full = "FREE"
            ui_panels.ui_message(
                title="All BlenderKit materials are free",
                message="Any material uploaded to BlenderKit is free."
                " However, it can still earn money for the author,"
                " based on our fair share system. "
                "Part of subscription is sent to artists based on usage by paying users.",
            )


def can_edit_asset(active_index=-1, asset_data=None):
    if active_index < 0 and not asset_data:
        return False
    profile = global_vars.DATA.get("bkit profile")
    if profile is None:
        return False
    if utils.profile_is_validator():
        return True
    if not asset_data:
        sr = global_vars.DATA["search results"]
        asset_data = dict(sr[active_index])
    if int(asset_data["author"]["id"]) == int(profile["user"]["id"]):
        return True
    return False


class FastMetadata(bpy.types.Operator):
    """Edit metadata of the asset"""

    bl_idname = "wm.blenderkit_fast_metadata"
    bl_label = "Update metadata"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    asset_id: StringProperty(
        name="Asset Base Id",
        description="Unique name of the asset (hidden)",
        default="",
    )
    asset_type: StringProperty(name="Asset Type", description="Asset Type", default="")
    name: StringProperty(
        name="Name",
        description="Main name of the asset",
        default="",
    )
    description: StringProperty(
        name="Description", description="Description of the asset", default=""
    )
    tags: StringProperty(
        name="Tags",
        description="List of tags, separated by commas (optional)",
        default="",
    )
    category: EnumProperty(
        name="Category",
        description="Select the main category for the uploaded asset",
        items=categories.get_category_enums,
        update=categories.update_category_enums,
    )
    subcategory: EnumProperty(
        name="Subcategory",
        description="Select a subcategory within the chosen main category",
        items=categories.get_subcategory_enums,
        update=categories.update_subcategory_enums,
    )
    subcategory1: EnumProperty(
        name="Sub-subcategory",
        description="Select a further subcategory within the chosen subcategory",
        items=categories.get_subcategory1_enums,
    )
    license: EnumProperty(
        items=licenses,
        default="royalty_free",
        description="License. Please read our help for choosing the right licenses",
    )
    is_private: EnumProperty(
        name="Thumbnail Style",
        items=(
            (
                "PRIVATE",
                "Private",
                "You asset will be hidden to public. The private assets are limited by a quota.",
            ),
            (
                "PUBLIC",
                "Public",
                '"Your asset will go into the validation process automatically',
            ),
        ),
        description="If not marked private, your asset will go into the validation process automatically\n"
        "Private assets are limited by quota",
        default="PUBLIC",
    )

    free_full: EnumProperty(
        name="Free or Full Plan",
        items=(
            (
                "FREE",
                "Free",
                "You consent you want to release this asset as free for everyone",
            ),
            ("FULL", "Full", "Your asset will be in the full plan"),
        ),
        description="Choose whether the asset should be free or in the Full Plan",
        default="FULL",
        update=update_free_full,
    )

    ####################

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        # col = layout.column()
        layout.label(text=self.message)
        layout.prop(self, "category")
        if self.category != "NONE" and self.subcategory != "EMPTY":
            layout.prop(self, "subcategory")
        if self.subcategory != "NONE" and self.subcategory1 != "EMPTY":
            layout.prop(self, "subcategory1")
        layout.prop(self, "name")
        layout.prop(self, "description")
        layout.prop(self, "tags")
        layout.prop(self, "is_private", expand=True)
        layout.prop(self, "free_full", expand=True)
        if self.is_private == "PUBLIC":
            layout.prop(self, "license")

    def execute(self, context):
        if self.subcategory1 not in ("NONE", "EMPTY"):
            category = self.subcategory1
        elif self.subcategory not in ("NONE", "EMPTY"):
            category = self.subcategory
        else:
            category = self.category
        utils.update_tags(self, context)
        metadata = {
            "category": category,
            "displayName": self.name,
            "description": self.description,
            "tags": utils.string2list(self.tags),
            "isPrivate": self.is_private == "PRIVATE",
            "isFree": self.free_full == "FREE",
            "license": self.license,
        }
        url = f"{paths.BLENDERKIT_API}/assets/{self.asset_id}/"
        api_key = bpy.context.preferences.addons["blenderkit"].preferences.api_key
        headers = utils.get_headers(api_key)
        messages = {
            "success": "Metadata upload succeded",
            "error": "Metadata upload failed",
        }
        daemon_lib.nonblocking_request(url, "PATCH", headers, metadata, messages)
        return {"FINISHED"}

    def invoke(self, context, event):
        ui_props = bpy.context.window_manager.blenderkitUI
        if ui_props.active_index > -1:
            sr = global_vars.DATA["search results"]
            asset_data = dict(sr[ui_props.active_index])
        else:
            active_asset = utils.get_active_asset_by_type(asset_type=self.asset_type)
            asset_data = active_asset.get("asset_data")

        if not can_edit_asset(asset_data=asset_data):
            return {"CANCELLED"}
        self.asset_id = asset_data["id"]
        self.asset_type = asset_data["assetType"]
        cat_path = categories.get_category_path(
            global_vars.DATA["bkit_categories"], asset_data["category"]
        )
        try:
            if len(cat_path) > 1:
                self.category = cat_path[1]
            if len(cat_path) > 2:
                self.subcategory = cat_path[2]
        except Exception as e:
            bk_logger.error(e)

        self.message = f"Fast edit metadata of {asset_data['displayName']}"
        self.name = asset_data["displayName"]
        self.description = asset_data["description"]
        self.tags = ",".join(asset_data["tags"])
        if asset_data["isPrivate"]:
            self.is_private = "PRIVATE"
        else:
            self.is_private = "PUBLIC"

        if asset_data["isFree"]:
            self.free_full = "FREE"
        else:
            self.free_full = "FULL"
        self.license = asset_data["license"]

        wm = context.window_manager

        return wm.invoke_props_dialog(self, width=600)


def get_upload_location(props):
    """
    not used by now, gets location of uploaded asset - potentially usefull if we draw a nice upload gizmo in viewport.
    Parameters
    ----------
    props

    Returns
    -------

    """
    ui_props = bpy.context.window_manager.blenderkitUI
    if ui_props.asset_type == "MODEL":
        if bpy.context.view_layer.objects.active is not None:
            ob = utils.get_active_model()
            return ob.location
    if ui_props.asset_type == "SCENE":
        return None
    elif ui_props.asset_type == "MATERIAL":
        if (
            bpy.context.view_layer.objects.active is not None
            and bpy.context.active_object.active_material is not None
        ):
            return bpy.context.active_object.location
    elif ui_props.asset_type == "TEXTURE":
        return None
    elif ui_props.asset_type == "BRUSH":
        return None
    return None


def storage_quota_available(props) -> bool:
    """Check the storage quota if there is available space to upload."""
    profile = global_vars.DATA.get("bkit profile")
    if profile is None:
        props.report = "Please log-in first."
        return False

    if props.is_private == "PUBLIC":
        return True

    quota = profile["user"].get("remainingPrivateQuota", 0)
    if quota > 0:
        return True

    props.report = "Private storage quota exceeded."
    return False


def auto_fix(asset_type=""):
    # this applies various procedures to ensure coherency in the database.
    asset = utils.get_active_asset()
    props = utils.get_upload_props()
    if asset_type == "MATERIAL":
        overrides.ensure_eevee_transparency(asset)
        asset.name = props.name


def prepare_asset_data(self, context, asset_type, reupload, upload_set):
    """Process asset and its data for upload."""
    props = utils.get_upload_props()
    utils.name_update(props)  # fix the name first

    if storage_quota_available(props) is False:
        self.report({"ERROR_INVALID_INPUT"}, props.report)
        return False, None, None

    auto_fix(asset_type=asset_type)

    # do this for fixing long tags in some upload cases
    props.tags = props.tags[:]

    # check for missing metadata
    upload_thumbnail = "THUMBNAIL" in upload_set
    check_missing_data(asset_type, props, upload_thumbnail=upload_thumbnail)
    # if previous check did find any problems then
    if props.report != "":
        return False, None, None

    if not reupload:
        props.asset_base_id = ""
        props.id = ""

    export_data, upload_data = get_upload_data(
        caller=self, context=context, asset_type=asset_type
    )

    # check if thumbnail exists, generate for HDR:
    if "THUMBNAIL" in upload_set:
        if asset_type == "HDR":
            image_utils.generate_hdr_thumbnail()
            # get upload data because the image utils function sets true_hdr
            export_data, upload_data = get_upload_data(
                caller=self, context=context, asset_type=asset_type
            )

        elif not os.path.exists(export_data["thumbnail_path"]):
            props.upload_state = "0% - thumbnail not found"
            props.uploading = False
            return False, None, None

    # save a copy of the file for processing. Only for blend files
    _, ext = os.path.splitext(bpy.data.filepath)
    if not ext:
        ext = ".blend"
    export_data["temp_dir"] = tempfile.mkdtemp()
    export_data["source_filepath"] = os.path.join(
        export_data["temp_dir"], "export_blenderkit" + ext
    )
    if asset_type != "HDR":
        # if this isn't here, blender crashes.
        if bpy.app.version >= (3, 0, 0):
            bpy.context.preferences.filepaths.file_preview_type = "NONE"

        bpy.ops.wm.save_as_mainfile(
            filepath=export_data["source_filepath"], compress=False, copy=True
        )

    export_data["binary_path"] = bpy.app.binary_path
    export_data["debug_value"] = bpy.app.debug_value

    return True, upload_data, export_data


asset_types = (
    ("MODEL", "Model", "Set of objects"),
    ("SCENE", "Scene", "Scene"),
    ("HDR", "HDR", "HDR image"),
    ("MATERIAL", "Material", "Any .blend Material"),
    ("TEXTURE", "Texture", "A texture, or texture set"),
    ("BRUSH", "Brush", "Brush, can be any type of blender brush"),
    ("ADDON", "Addon", "Addon"),
)


class UploadOperator(Operator):
    """Tooltip"""

    bl_idname = "object.blenderkit_upload"
    bl_description = "Upload or re-upload asset + thumbnail + metadata"

    bl_label = "BlenderKit asset upload"
    bl_options = {"REGISTER", "INTERNAL"}

    # type of upload - model, material, textures, e.t.c.
    asset_type: EnumProperty(
        name="Type",
        items=asset_types,
        description="Type of upload",
        default="MODEL",
    )

    reupload: BoolProperty(
        name="reupload",
        description="reupload but also draw so that it asks what to reupload",
        default=False,
        options={"SKIP_SAVE"},
    )

    metadata: BoolProperty(name="metadata", default=False, options={"SKIP_SAVE"})

    thumbnail: BoolProperty(name="thumbnail", default=False, options={"SKIP_SAVE"})

    main_file: BoolProperty(name="main file", default=False, options={"SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return utils.uploadable_asset_poll()

    def execute(self, context):
        bpy.ops.object.blenderkit_auto_tags()
        props = utils.get_upload_props()

        upload_set = []
        if not self.reupload:
            upload_set = ["METADATA", "THUMBNAIL", "MAINFILE"]
        else:
            if self.metadata:
                upload_set.append("METADATA")
            if self.thumbnail:
                upload_set.append("THUMBNAIL")
            if self.main_file:
                upload_set.append("MAINFILE")
        if upload_set == []:
            self.report(
                {"ERROR"},
                "No components selected for reupload. Please select at least one from: metadata, main file, or thumbnail to reupload.",
            )
            return {"CANCELLED"}

        # this is accessed later in get_upload_data and needs to be written.
        # should pass upload_set all the way to it probably
        if "MAINFILE" in upload_set:
            self.main_file = True

        ok, upload_data, export_data = prepare_asset_data(
            self, context, self.asset_type, self.reupload, upload_set=upload_set
        )
        if not ok:
            self.report({"ERROR_INVALID_INPUT"}, props.report)
            props.upload_state = ""
            return {"CANCELLED"}

        props.upload_state = "0% - preparing upload"
        props.uploading = True

        daemon_lib.upload_asset(upload_data, export_data, upload_set)
        return {"FINISHED"}

    def draw(self, context):
        props = utils.get_upload_props()
        layout = self.layout

        if self.reupload:
            utils.label_multiline(
                layout,
                text=(
                    "Select the components of the asset you wish to update through reupload. "
                    "For editing metadata and thumbnails, you can also use the web interface linked above."
                ),
                width=500,
            )
            layout.prop(self, "metadata")
            layout.prop(self, "main_file")
            layout.prop(self, "thumbnail")

        if props.asset_base_id != "" and not self.reupload:
            utils.label_multiline(
                layout,
                text="Really upload as new?\n\n"
                "Do this only when you create a new asset from an old one.\n"
                "For updates of thumbnail or model use reupload.\n",
                width=400,
                icon="ERROR",
            )

        if props.is_private == "PUBLIC":
            if self.asset_type == "MODEL":
                utils.label_multiline(
                    layout,
                    text="\nYou marked the asset as public. "
                    "This means it will be validated by our team.\n\n"
                    "Please test your upload after it finishes:\n"
                    "-   Open a new file\n"
                    "-   Find the asset and download it\n"
                    "-   Check if it snaps correctly to surfaces\n"
                    "-   Check if it has all textures and renders as expected\n"
                    "-   Check if it has correct size in world units (for models)",
                    width=400,
                )
            elif self.asset_type == "HDR":
                if not props.true_hdr:
                    utils.label_multiline(
                        layout,
                        text="This image isn't HDR,\n"
                        "It has a low dynamic range.\n"
                        "BlenderKit library accepts 360 degree images\n"
                        "however the default filter setting for search\n"
                        "is to show only true HDR images\n",
                        icon="ERROR",
                        width=500,
                    )

                utils.label_multiline(
                    layout,
                    text="You marked the asset as public. "
                    "This means it will be validated by our team.\n\n"
                    "Please test your upload after it finishes:\n"
                    "-   Open a new file\n"
                    "-   Find the asset and download it\n"
                    "-   Check if it works as expected\n",
                    width=500,
                )
            else:
                utils.label_multiline(
                    layout,
                    text="You marked the asset as public."
                    "This means it will be validated by our team.\n\n"
                    "Please test your upload after it finishes:\n"
                    "-   Open a new file\n"
                    "-   Find the asset and download it\n"
                    "-   Check if it works as expected\n",
                    width=500,
                )

    def invoke(self, context, event):
        if not utils.user_logged_in():
            ui_panels.draw_not_logged_in(
                self, message="To upload assets you need to login/signup."
            )
            return {"CANCELLED"}

        if self.asset_type == "HDR":
            # getting upload data for images ensures true_hdr check so users can be informed about their handling
            # simple 360 photos or renders with LDR are hidden by default..
            export_data, upload_data = get_upload_data(asset_type="HDR")

        # if props.is_private == 'PUBLIC':
        return context.window_manager.invoke_props_dialog(self, width=500)
        # else:
        #     return self.execute(context)


class AssetDebugPrint(Operator):
    """Change verification status"""

    bl_idname = "object.blenderkit_print_asset_debug"
    bl_description = "BlenderKit print asset data for debug purposes"
    bl_label = "BlenderKit print asset data"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    # type of upload - model, material, textures, e.t.c.
    asset_id: StringProperty(
        name="asset id",
    )

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        if not global_vars.DATA["search results"]:
            print("no search results found")
            return {"CANCELLED"}
        # update status in search results for validator's clarity
        sr = global_vars.DATA["search results"]

        result = None
        for r in sr:
            if r["id"] == self.asset_id:
                result = r
        if not result:
            ad = bpy.context.active_object.get("asset_data")
            if ad:
                result = ad.to_dict()
        if result:
            t = bpy.data.texts.new(result["displayName"])
            t.write(json.dumps(result, indent=4, sort_keys=True))
            print(json.dumps(result, indent=4, sort_keys=True))
        return {"FINISHED"}


class AssetVerificationStatusChange(Operator):
    """Change verification status"""

    bl_idname = "object.blenderkit_change_status"
    bl_description = "Change asset status"
    bl_label = "Change verification status"
    bl_options = {"REGISTER", "UNDO", "INTERNAL"}

    # type of upload - model, material, textures, e.t.c.
    asset_id: StringProperty(
        name="asset id",
    )

    state: StringProperty(name="verification_status", default="uploaded")

    original_state: StringProperty(name="verification_status", default="uploaded")

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        # if self.state == 'deleted':
        message = "Really delete asset from BlenderKit online storage?"
        if self.original_state == "on_hold":
            message += (
                "\n\nThis asset is on hold. If you want to upload it again,"
                " please reupload the asset instead of deleting it and "
                "uploading it as a new one. "
                "This will preserve the validation history in the comments and avoid any misunderstandings."
            )
        utils.label_multiline(layout, text=message, width=300)

        # layout.prop(self, 'state')

    def execute(self, context):
        if not global_vars.DATA["search results"]:
            return {"CANCELLED"}
        # update status in search results for validator's clarity
        search_results = global_vars.DATA["search results"]
        for result in search_results:
            if result["id"] == self.asset_id:
                result["verificationStatus"] = self.state

        url = paths.BLENDERKIT_API + "/assets/" + str(self.asset_id) + "/"
        headers = utils.get_headers(
            bpy.context.preferences.addons["blenderkit"].preferences.api_key
        )
        upload_data = {"verificationStatus": self.state}
        messages = {
            "success": "Verification status changed",
            "error": "Verification status change failed",
        }
        daemon_lib.nonblocking_request(url, "PATCH", headers, upload_data, messages)

        if asset_bar_op.asset_bar_operator is not None:
            asset_bar_op.asset_bar_operator.update_layout(context, None)
        return {"FINISHED"}

    def invoke(self, context, event):
        # print(self.state)
        if self.state == "deleted":
            wm = context.window_manager
            return wm.invoke_props_dialog(self)
        return {"RUNNING_MODAL"}


def handle_asset_upload(task: daemon_tasks.Task):
    asset = eval(f"{task.data['export_data']['eval_path']}.blenderkit")
    asset.upload_state = f"{task.progress}% - {task.message}"
    if task.status == "error":
        asset.uploading = False
        return reports.add_report(task.message, type="ERROR")

    if task.status == "finished":
        asset.uploading = False
        return reports.add_report("Upload successfull")


def handle_asset_metadata_upload(task: daemon_tasks.Task):
    asset = eval(f"{task.data['export_data']['eval_path']}.blenderkit")

    if task.status != "finished":
        return

    new_asset_base_id = task.data["asset_data"].get("assetBaseId")
    if new_asset_base_id is not None:
        asset.asset_base_id = new_asset_base_id
        bk_logger.info(f"Assigning new asset.asset_base_id: {new_asset_base_id}")
    else:
        asset.asset_base_id = task.data["export_data"]["assetBaseId"]

    new_asset_id = task.data["asset_data"].get("id")
    if new_asset_id is not None:
        asset.id = new_asset_id
        bk_logger.info(f"Assigning new asset.id: {new_asset_id}")
    else:
        asset.id = task.data["export_data"]["id"]

    return reports.add_report("Metadata upload successfull")


def register_upload():
    bpy.utils.register_class(UploadOperator)
    bpy.utils.register_class(FastMetadata)
    bpy.utils.register_class(AssetDebugPrint)
    bpy.utils.register_class(AssetVerificationStatusChange)


def unregister_upload():
    bpy.utils.unregister_class(UploadOperator)
    bpy.utils.unregister_class(FastMetadata)
    bpy.utils.unregister_class(AssetDebugPrint)
    bpy.utils.unregister_class(AssetVerificationStatusChange)
