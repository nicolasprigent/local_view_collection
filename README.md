# Local View by Collection (Blender Add-on)

This addon shows a collection hierarchy in the 3D viewsport to quickly isolate into local view the objects of a collection. Use `Numpad *` to see the popup.

## Usage
- `Numpad *`: popup shows Collection hierarchy
  - With selection: only parent paths of the selected objects' Collections
  - Without selection: full View Layer Collections tree
- Click on a collection name to set local view on all objects in it, including the ones in child collection
- Automatically enters Local View when selecting a collection if not already active.
- `Numpad /` to toggle Local View manually if needed

## Customization
- Change the hierarchy keymap: Preferences → Keymap → Window → bind `view3d.collection_hierarchy_popup`.
- Restore the Local View popup: Preferences → Keymap → 3D View → add a key for `wm.call_menu` with name `VIEW3D_MT_local_view_collections`.
- Include child collections in isolation: operator includes child collections by default.

## Notes
- The shortcut uses Numpad `*` (no modifier). You can change it in Preferences → Keymap.
- The add-on does not change your selection or object visibility; it sets Local View membership for objects directly and will enter Local View automatically.
- Should work on Blender 3.0+ (tested on 3.3.21)