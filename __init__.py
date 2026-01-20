bl_info = {
    "name": "Local View by Collection",
    "author": "D3W3",
    "version": (1, 0, 1),
    "blender": (3, 0, 0),
    "location": "3D View",
    "description": "Show collection hierarchy in 3D viewsport to quickly isolate into local view the objects of a collection. Use Numpad * to see the popup.",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}

import bpy
from bpy.types import Operator, Menu
from bpy.props import StringProperty, BoolProperty

# Store addon keymaps so they can be cleaned up on unregister
addon_keymaps = []


def _get_3dview_area(context):
    # Prefer the area where the operator was invoked; otherwise find any VIEW_3D
    area = getattr(context, "area", None)
    if area and area.type == 'VIEW_3D':
        return area
    for a in context.window.screen.areas:
        if a.type == 'VIEW_3D':
            return a
    return None


def _get_window_region(area):
    if not area:
        return None
    for r in area.regions:
        if r.type == 'WINDOW':
            return r
    return None


def _get_view3d_space(area):
    if not area:
        return None
    # Return the active VIEW_3D space or the first one
    space = getattr(area, 'spaces', None)
    if not space:
        return None
    if getattr(area.spaces, 'active', None) and area.spaces.active.type == 'VIEW_3D':
        return area.spaces.active
    for s in area.spaces:
        if s.type == 'VIEW_3D':
            return s
    return None


def _is_in_local_view(space):
    # Blender exposes local view state on SpaceView3D; it's truthy when active
    try:
        lv = getattr(space, 'local_view', None)
        return bool(lv)
    except Exception:
        return False

def _ensure_local_view_active(context, area, region, space, view_layer, target_objs):
    if _is_in_local_view(space):
        return True
    try:
        bpy.ops.view3d.localview(frame_selected=False)
    except Exception:
        pass
    if _is_in_local_view(space):
        return True
    # If we have targets, temporarily select them to enter Local View, then deselect
    if target_objs:
        try:
            visible_targets = [o for o in target_objs if o and getattr(o, 'visible_get', lambda: True)()]
        except Exception:
            visible_targets = list(target_objs)

        if not visible_targets:
            return False

        try:
            if getattr(context, 'mode', 'OBJECT') != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass

        try:
            bpy.ops.object.select_all(action='DESELECT')
        except Exception:
            pass

        first = None
        for o in visible_targets:
            try:
                o.select_set(True)
                if first is None:
                    first = o
            except Exception:
                pass
        if first is not None:
            try:
                view_layer.objects.active = first
            except Exception:
                pass

        try:
            bpy.ops.view3d.localview(frame_selected=False)
        except Exception:
            pass

        try:
            bpy.ops.object.select_all(action='DESELECT')
        except Exception:
            pass

        return _is_in_local_view(space)
    return False

def _target_objects_from_collections(collections, include_children=True):
    """Return a flat, deduplicated list of objects from collections.
    Used to build target_objs for Local View and membership updates."""
    seen = set()
    result = []
    for coll in collections:
        if coll is None:
            continue
        try:
            objs_src = None
            if include_children and hasattr(coll, 'all_objects'):
                objs_src = coll.all_objects
            else:
                objs_src = getattr(coll, 'objects', [])
            for obj in objs_src:
                if obj and obj.name not in seen:
                    seen.add(obj.name)
                    result.append(obj)
        except Exception:
            # Fallback: try plain objects list
            for obj in list(getattr(coll, 'objects', [])):
                if obj and obj.name not in seen:
                    seen.add(obj.name)
                    result.append(obj)
    return result


class VIEW3D_OT_local_view_collection_activate(Operator):
    """Select all objects in the chosen Collection and toggle Local View"""
    bl_idname = "view3d.local_view_collection_activate"
    bl_label = "Local View: Activate Collection"
    bl_options = {'REGISTER', 'UNDO'}

    collection_name: StringProperty(name="Collection", default="")
    collection_names: StringProperty(name="Collections", default="")
    include_children: BoolProperty(name="Include Child Collections", default=True)

    def execute(self, context):
        names = []
        if self.collection_names.strip():
            names.extend([n for n in self.collection_names.split('\n') if n])
        elif self.collection_name:
            names.append(self.collection_name)
        else:
            self.report({'WARNING'}, "No collection provided")
            return {'CANCELLED'}

        collections = [bpy.data.collections.get(n) for n in names]
        collections = [c for c in collections if c is not None]
        if not collections:
            self.report({'WARNING'}, "No valid collections provided")
            return {'CANCELLED'}

        area = _get_3dview_area(context)
        region = _get_window_region(area)
        space = _get_view3d_space(area)
        if area is None or region is None or space is None:
            self.report({'WARNING'}, "No active 3D View found")
            return {'CANCELLED'}
        view_layer = context.view_layer

        try:
            # Use temp_override for robust operator context in Blender 3.x+
            with bpy.context.temp_override(window=context.window,
                                           screen=context.window.screen,
                                           area=area,
                                           region=region,
                                           space_data=space,
                                           scene=context.scene,
                                           view_layer=view_layer):
                # Build union of target objects across provided collections
                target_objs = _target_objects_from_collections(collections, self.include_children)
                # Ensure the viewport is in Local View;
                if not _ensure_local_view_active(context, area, region, space, view_layer, target_objs):
                    self.report({'ERROR'}, "Could not activate Local View automatically")
                    return {'CANCELLED'}

                # Build target object name set
                target_names = {obj.name for obj in target_objs}

                # Set local view membership per object, no selection/visibility changes
                for obj in context.scene.objects:
                    try:
                        obj.local_view_set(space, obj.name in target_names)
                    except Exception:
                        pass
        except Exception as e:
            self.report({'ERROR'}, f"Failed to toggle Local View: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


## Removed: VIEW3D_OT_local_view_collections_activate (merged into single operator above)


def _find_layer_collection_path(node, target_collection):
    """Return list of LayerCollection nodes from root to target, or None."""
    try:
        if node.collection == target_collection:
            return [node]
    except Exception:
        pass
    for child in getattr(node, 'children', []):
        path = _find_layer_collection_path(child, target_collection)
        if path:
            return [node] + path
    return None


def _build_full_layer_tree_entries(root_layer_col):
    """Return list of (display_text, Collection, selectable) for full hierarchy."""
    entries = []

    def rec(node, prefix, is_last):
        coll = getattr(node, 'collection', None)
        name = getattr(coll, 'name', '(unknown)')
        # Root printed without connector when prefix is empty
        if prefix:
            connector = '└─ ' if is_last else '├─ '
            text = prefix + connector + name
        else:
            text = name
        selectable = bool(prefix)  # Root has empty prefix → not selectable
        entries.append((text, coll, selectable))
        children = list(getattr(node, 'children', []))
        count = len(children)
        for i, child in enumerate(children):
            next_prefix = prefix + ('   ' if is_last else '│  ')
            rec(child, next_prefix, i == count - 1)

    rec(root_layer_col, '', True)
    return entries


def _build_path_entries(path_nodes):
    """Return list of (display_text, Collection, selectable) for a single path."""
    entries = []
    for i, node in enumerate(path_nodes):
        coll = getattr(node, 'collection', None)
        name = getattr(coll, 'name', '(unknown)')
        if i == 0:
            text = name
            selectable = False  # Root (Scene Collection) not selectable
        else:
            text = ('   ' * (i - 1)) + '└─ ' + name
            selectable = True
        entries.append((text, coll, selectable))
    return entries


class VIEW3D_OT_collection_hierarchy_popup(Operator):
    """Display the Collections hierarchy (including parents).\n\nWith a selection: shows all parent Collection paths for the selected objects.\nWithout a selection: shows the full Collections hierarchy of the active View Layer."""
    bl_idname = "view3d.collection_hierarchy_popup"
    bl_label = "Collections: Hierarchy"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        vl = context.view_layer
        if not vl:
            self.report({'WARNING'}, "No active View Layer")
            return {'CANCELLED'}

        root = vl.layer_collection
        entries = []
        disabled_labels = []

        selected = list(context.selected_objects)
        if selected:
            if len(selected) > 1:
                # Multiple selection: union of direct parent collections for all selected objects
                union_colls = set()
                for obj in selected:
                    for coll in getattr(obj, 'users_collection', []):
                        union_colls.add(coll)

                # Trigger Local View for the union directly; no popup needed
                names = "\n".join([c.name for c in sorted(union_colls, key=lambda c: c.name.lower())])
                bpy.ops.view3d.local_view_collection_activate('INVOKE_DEFAULT',
                                                              collection_names=names,
                                                              include_children=True)
                return {'FINISHED'}
            else:
                # Single selection: show path entries for that object's collections
                obj = selected[0]
                for coll in sorted(getattr(obj, 'users_collection', []), key=lambda c: c.name.lower()):
                    path = _find_layer_collection_path(root, coll)
                    if path:
                        entries.extend(_build_path_entries(path))
                    else:
                        disabled_labels.append(f"(Outside View Layer) {coll.name}")
        else:
            entries = _build_full_layer_tree_entries(root)

        def draw(self_draw, ctx):
            layout = self_draw.layout
            col = layout.column(align=False)
            for text, coll, selectable in entries:
                # Clickable operator entries per collection
                if coll is not None and selectable:
                    op = col.operator(VIEW3D_OT_local_view_collection_activate.bl_idname,
                                      text=text, icon='OUTLINER_COLLECTION')
                    op.collection_name = getattr(coll, 'name', '')
                    op.include_children = True
                else:
                    row = col.row()
                    row.enabled = False
                    row.label(text=text, icon='OUTLINER_COLLECTION')
            # Non-clickable labels for collections outside the current View Layer
            if disabled_labels:
                col.separator()
                for lbl in disabled_labels:
                    row = col.row()
                    row.enabled = False
                    row.label(text=lbl, icon='ERROR')

        try:
            context.window_manager.popup_menu(draw, title="Collection Hierarchy", icon='OUTLINER_COLLECTION')
        except Exception:
            # Fallback: show as a simple dialog
            context.window_manager.invoke_props_dialog(self)
        return {'FINISHED'}


class VIEW3D_MT_local_view_collections(Menu):
    bl_label = "Local View by Collection"
    bl_idname = "VIEW3D_MT_local_view_collections"

    def draw(self, context):
        layout = self.layout
        selected = list(context.selected_objects)

        # Build the collection list: either all collections or those of selected objects
        collections_set = set()
        if selected:
            for obj in selected:
                for coll in getattr(obj, 'users_collection', []):
                    collections_set.add(coll)
        else:
            for coll in bpy.data.collections:
                collections_set.add(coll)

        # Sort by name and draw as operator entries
        for coll in sorted(collections_set, key=lambda c: c.name.lower()):
            op = layout.operator(VIEW3D_OT_local_view_collection_activate.bl_idname, text=coll.name)
            op.collection_name = coll.name
            op.include_children = True


def register():
    bpy.utils.register_class(VIEW3D_OT_local_view_collection_activate)
    bpy.utils.register_class(VIEW3D_MT_local_view_collections)
    bpy.utils.register_class(VIEW3D_OT_collection_hierarchy_popup)

    # Keymap: Numpad * opens the menu in 3D View
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='Window', space_type='EMPTY')
        # Some Blender builds use NUMPAD_ASTERIX, others NUMPAD_ASTERISK
        kmi = None
        try:
            kmi = km.keymap_items.new(VIEW3D_OT_collection_hierarchy_popup.bl_idname, 'NUMPAD_ASTERIX', 'PRESS')
        except Exception:
            try:
                kmi = km.keymap_items.new(VIEW3D_OT_collection_hierarchy_popup.bl_idname, 'NUMPAD_ASTERISK', 'PRESS')
            except Exception:
                # Fallback: Ctrl + Numpad /
                kmi = km.keymap_items.new(VIEW3D_OT_collection_hierarchy_popup.bl_idname, 'NUMPAD_SLASH', 'PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))


def unregister():
    # Remove keymap items
    try:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
    finally:
        addon_keymaps.clear()

    bpy.utils.unregister_class(VIEW3D_MT_local_view_collections)
    bpy.utils.unregister_class(VIEW3D_OT_local_view_collection_activate)
    bpy.utils.unregister_class(VIEW3D_OT_collection_hierarchy_popup)


if __name__ == "__main__":
    register()
