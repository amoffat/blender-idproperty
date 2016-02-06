"""
This module adds the concept of an IDProperty (like an IntProperty, or
StringProperty).  The IDProperty allows us to link to another object by name,
will stay linked even if that object's name changes, and will automatically
unlink if that object goes away.

Technically, this is accomplished by giving every object a unique id, accessed
by the .id attribute.  In order to put a unique id on every object, we decide to
lazily generate the ids -- only at the time of accessing the id attribute will
the id be created, if it doesn't already exist.  This allows the appearance of
every object to have an id automatically.

Also, if data is linked from one scene to another, the linked object in the new
scene may have an id that is taken by another object in the scene.  In this
case, any reference to the id may be incorrect, since we have no way of knowing
which object is the authentic one.

Random note to Blender devs: I love Blender and have been using it for over 10
years!  Thanks for all your hard work!  If there is any interest in bringing
this functionality to core, I would love to chat about it.  I think it could be
achieved relatively simply, just by introducing unique ids to native objects,
enforcing their uniqueness even in the case of duplication/linking, and
introducing a fast lookup from id -> object.
"""


import bpy
from bpy.app import handlers
from bpy.utils import register_module, unregister_module
from bpy import props as p
from contextlib import contextmanager
import json


bl_info = {
    "name": "IDProperty",
    "description": "Provides a new property type that allows you to point a \
property to another object, even if that object changes its name.",
    "category": "Object",
    "author": "Andrew Moffat",
    "version": (1, 2),
    "blender": (2, 7, 6)
}



# some arbitrarily large number representing the range of a set of ids within a
# library.  we use this in case a model has been linked to the current scene
# from a library, in which case, ids may be conflicting.  we'll use this number
# to help determine an offset to the linked object's id
LIB_ID_SPACE = 10000000

ID_TO_HASH = {}
HASH_TO_NAME = {}

SUPPORTED_COLLECTIONS = (
    ("objects", "Object"),
    ("materials", "Material"),
    ("groups", "Group"),
    ("libraries", "Library"),
)


class IDPropertyOpMixin(object):
    bl_label = ""
    to_populate_data = p.StringProperty()
    to_populate_field = p.StringProperty()


    @property
    def ob(self):
        data = eval(self.to_populate_data)
        ob_name = getattr(data, self.to_populate_field)
        return bpy.data.objects.get(ob_name)

    @ob.setter
    def ob(self, new_ob):
        ob_name = new_ob.name if new_ob else ""
        data = eval(self.to_populate_data)
        setattr(data, self.to_populate_field, ob_name)

    @classmethod
    def poll(self, ctx):
        return has_active_3d_view()


class SelectedToIdProperty(IDPropertyOpMixin, bpy.types.Operator):
    bl_idname = "idproperty.get_selected"

    def execute(self, ctx):
        sel = ctx.selected_objects
        ob = None
        if len(sel) > 1:
            ob = sel[0]

        self.ob = ob
        return {"FINISHED"}


class FindSelected(IDPropertyOpMixin, bpy.types.Operator):
    bl_idname = "idproperty.find_selected"

    def execute(self, ctx):
        if self.ob:
            for ob in ctx.scene.objects:
                ob.select = False

            ctx.scene.objects.active = self.ob
            self.ob.select = True

            with in_3dview(ctx) as override:
                bpy.ops.view3d.view_selected(override)

        return {"FINISHED"}


def has_active_3d_view():
    return len(list(all_3d_views())) > 0

def all_3d_views():
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            for region in area.regions:
                if region.type == "WINDOW":
                    yield (area, region)


@contextmanager
def in_3dview(ctx):
    try:
        area, region = list(all_3d_views())[0]
    except IndexError:
        raise Exception("no 3d region found")

    override = ctx.copy()
    override.update({"area": area, "region": region})
    yield override



def layout_id_prop(layout, data, prop):
    prop_obj = data.bl_rna.properties[prop]
    prop_name = prop_obj.name
    value_key = _create_value_key(prop_name)
    ref_id = data.get(value_key, None)

    field_name = json.loads(prop_obj.description)["field_name"]

    row = layout.row(align=True)
    row.prop_search(data, prop, bpy.data, field_name)

    if field_name == "objects":
        op_props = row.operator(SelectedToIdProperty.bl_idname, emboss=True, icon="EYEDROPPER")
        op_props.to_populate_data = repr(data)
        op_props.to_populate_field = prop

        op_props = row.operator(FindSelected.bl_idname, emboss=True, icon="VIEWZOOM")
        op_props.to_populate_data = repr(data)
        op_props.to_populate_field = prop


def _get_global_id(field):
    """ internal helper for getting the true unique counter id by looking
    at all scenes and picking the highest value """
    field += "_id_counter"
    scenes = list(bpy.data.scenes)
    scenes.sort(key=lambda s: getattr(s, field), reverse=True)
    max_id = getattr(scenes[0], field)
    return max_id

def _inc_global_id(field, old_max_id):
    """ internal helper for incrementing the unique object counter id by making
    sure that all scenes have the same value """
    field += "_id_counter"
    new_id = old_max_id + 1
    for scene in bpy.data.scenes:
        setattr(scene, field, new_id)
    return new_id



def get_by_id(data_field, id):
    data = getattr(bpy.data, data_field)

    id_to_hash = ID_TO_HASH[data_field]
    hash_to_name = HASH_TO_NAME[data_field]

    hash = id_to_hash.get(id, None)
    ob_name = hash_to_name.get(hash)

    ob = None
    if ob_name:
        ob = data.get(ob_name, None)

    return ob



def _create_id_getter(field):
    def fn(self):
        id = self.get("id", 0)
        if not id:
            id = _get_global_id(field)
            self["id"] = id
            _inc_global_id(field, id)

        # if our object lives in another blend file, and has been linked into this
        # file, we're going to offset all of its ids by some amount
        lib_offset = 0
        if self.library:
            lib_offset = (self.library.id+1) * LIB_ID_SPACE

        return id + lib_offset
    return fn


def _create_value_key(name):
    return name + "_id"


def create_getter(data_field, value_key):
    data = getattr(bpy.data, data_field)

    def fn(self):
        ob_id = self.get(value_key, None)

        ob_hash = ID_TO_HASH[data_field].get(ob_id, None)

        # has a reference to an object that no longer exists
        if ob_hash is None:
            ob = get_by_id(data_field, ob_id)
            if ob is not None:
                ob_hash = hash(ob)
                ID_TO_HASH[data_field][ob_id] = ob_hash
                HASH_TO_NAME[data_field][ob_hash] = ob.name

        ob_name = HASH_TO_NAME[data_field].get(ob_hash, None)
        exists = ob_name is not None and ob_name in data 

        if not exists:
            for name, ob in data.items():
                if ob_hash == hash(ob):
                    HASH_TO_NAME[data_field][ob_hash] = name
                    ob_name = name
                    break

        if ob_name is None:
            ob_name = ""
        return ob_name
    return fn



def create_setter(data_field, value_key, validator=None):
    data = getattr(bpy.data, data_field)

    def fn(self, value):
        if value == "":
            self[value_key] = 0

        else:
            ob = data.get(value, None)
            if ob:
                valid = True
                if validator:
                    valid = validator(ob)

                if valid:
                    ob_hash = hash(ob)
                    expected_hash = ID_TO_HASH[data_field].get(ob.id, None)

                    # the object is new, and doesn't have an entry in the hash
                    # lookup.  it is entirely possible that this is a duplicated
                    # object and it shares its id with other objects.  so let's
                    # re-evaluate its id
                    if ob_hash != expected_hash:
                        ob["id"] = 0
                        ID_TO_HASH[data_field][ob.id] = ob_hash
                        HASH_TO_NAME[data_field][ob_hash] = ob.name

                    self[value_key] = ob.id

    return fn


def _create_id_property(field_name):
    def fn(*args, **kwargs):
        """ the main class.  """
        value_key = _create_value_key(kwargs["name"])
        validator = kwargs.pop("validator", None)

        kwargs["get"] = create_getter(field_name, value_key)
        kwargs["set"] = create_setter(field_name, value_key, validator)

        payload = {
            "field_name": field_name,
        }
        kwargs["description"] = json.dumps(payload)

        prop = p.StringProperty(*args, **kwargs)
        return prop

    return fn


for col_name, type_name in SUPPORTED_COLLECTIONS:
    prop_name = type_name + "IDProperty"
    globals()[prop_name] = _create_id_property(col_name)



def load_file(_=None):
    for col_name, _ in SUPPORTED_COLLECTIONS:
        id_to_hash = {}
        hash_to_name = {}

        ID_TO_HASH[col_name] = id_to_hash
        HASH_TO_NAME[col_name] = hash_to_name

        col = getattr(bpy.data, col_name)
        all_obs = sorted(list(col), key=lambda ob: ob.name, reverse=True)

        for ob in all_obs:
            # on load, if we encounter an object with a dup id.  unset it and let it
            # regenerate as a unique id
            if ob.id in id_to_hash:
                ob["id"] = 0

            id_to_hash[ob.id] = hash(ob)
            hash_to_name[hash(ob)] = ob.name


@handlers.persistent
def register():
    bpy.utils.register_class(SelectedToIdProperty)
    bpy.utils.register_class(FindSelected)

    for col_name, type_name in SUPPORTED_COLLECTIONS:
        type = getattr(bpy.types, type_name)
        type.id = p.IntProperty(name="unique id", get=_create_id_getter(col_name))

        counter_name = col_name + "_id_counter"
        setattr(bpy.types.Scene, counter_name,
            p.IntProperty(name="unique id counter", default=1))


    handlers.load_post.append(load_file)
    load_file()


def unregister():
    bpy.utils.unregister_class(SelectedToIdProperty)
    bpy.utils.unregister_class(FindSelected)

    for col_name, type_name in SUPPORTED_COLLECTIONS:
        type = getattr(bpy.types, type_name)
        del type.id
        counter_name = col_name + "_id_counter"
        delattr(bpy.types.Scene, counter_name)

    handlers.load_post.remove(load_file)

    
try:
    unregister()
except:
    pass
register()
