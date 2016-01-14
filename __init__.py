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

There are conditions that can break the uniqueness of the ids.  If we duplicate
an object, this code has no way of knowing that the object was duplicated, and
so the .id property of the duplicate will be identical.  To resolve this, we
find all conflicting ids whenever an IDProperty is evaluated, and choose the
first object (as ordered in bpy.data.objects) to be the authentic object.  We
choose the first, because the duplicated object will have a name similar to
"name.001".  This assumption is incorrect if the duplicated object is renamed
before the id conflict is resolved.

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
from bpy.utils import register_module, unregister_module
from bpy import props as p


bl_info = {
    "name": "ID Properties",
    "description": "Provides a new property type that allows you to point a \
property to another object, even if that object changes its name.",
    "category": "Object",
    "author": "Andrew Moffat",
    "version": (1, 0),
    "blender": (2, 7, 6)
}



# some arbitrarily large number representing the range of a set of ids within a
# library.  we use this in case a model has been linked to the current scene
# from a library, in which case, ids may be conflicting.  we'll use this number
# to help determine an offset to the linked object's id
LIB_ID_SPACE = 10000000

# text used for when a id property reference is broken
NOT_FOUND = "<NOT FOUND>"


def layout_id_prop(layout, data, prop):
    """ a convenience function for wiring up any layout to an IDProperty.  this
    will set an nice icon for the field, as well as handle any alerting of the
    field based on whether we can find the object the field was pointing to

    instead of doing this:
        
        row = layout.row()
        row.prop(data, prop)

    do this:

        row = layout.row()
        layout_id_prop(row, data, prop)
    """
    # determine if our input should be in the alert state (red) based on whether
    # or not our reference to the object was broken
    prop_name = data.bl_rna.properties[prop].name
    value_key = _create_value_key(prop_name)
    ref_id = data.get(value_key, None)
    layout.alert = ref_id == -1

    layout.prop(data, prop, icon="OBJECT_DATA")



def resolve_ob_name(name):
    lib = None

    if "." in name:
        parts = name.split(".")
        lib_name = parts[0]
        rest = ".".join(parts[1:])

        lib = bpy.data.libraries.get(lib_name, None)


def _create_global_id_getter(field):
    def fn():
        """ internal helper for getting the true unique counter id by looking
        at all scenes and picking the highest value """
        scenes = list(bpy.data.scenes)
        scenes.sort(key=lambda s: getattr(s, field), reverse=True)
        max_id = getattr(scenes[0], field)
        return max_id
    return fn

def _create_global_id_inc(field):
    def fn(old_max_id):
        """ internal helper for incrementing the unique object counter id by making
        sure that all scenes have the same value """
        new_id = old_max_id + 1
        for scene in bpy.data.scenes:
            setattr(scene, field, new_id)
        return new_id
    return fn


_get_global_ob_id = _create_global_id_getter("ob_id_counter")
_get_global_lib_id = _create_global_id_getter("lib_id_counter")
_inc_global_ob_id = _create_global_id_inc("ob_id_counter")
_inc_global_lib_id = _create_global_id_inc("lib_id_counter")


def _resolve_id_conflicts(scene, conflicts):
    """ a utility function, used internally, to resolve id conflicts arising
    from object duplication.  we return the "correct" object and mutate all of
    the incorrect objects to have unique ids """

    resolved = conflicts[0]
    max_id = _get_global_ob_id()
    for ob in conflicts[1:]:
        ob["id"] = max_id
        max_id = _inc_global_ob_id(max_id)

    return resolved


def get_object_by_id(id):
    """ find an object by id.  this is slow, in that we have to iterate over
    every object in order to resolve conflicts introduced by duplicating
    objects.  but in practice, it's not that slow.  testing with 10000 objects,
    evaluation time was only about 0.01s """

    scene = bpy.context.scene

    have_same_id = []
    for ob in bpy.data.objects:
        if ob.id == id:
            have_same_id.append(ob)

    resolved = None

    # if we have conflicts, we need to adjust the ids of the conflicting
    # objects
    if have_same_id:
        resolved = _resolve_id_conflicts(scene, have_same_id)

    return resolved


def get_ob_id(self):
    """ the getter for an Object that returns the object's unique id.  if we
    don't have one, we generate one and increment the Scene.id_counter """
    id = self.get("id", None)
    if id is None:
        id = _get_global_ob_id()
        self["id"] = id
        _inc_global_ob_id(id)

    # if our object lives in another blend file, and has been linked into this
    # file, we're going to offset all of its ids by some amount
    lib_offset = 0
    if self.library:
        lib_offset = (self.library.id+1) * LIB_ID_SPACE

    return id + lib_offset


def get_lib_id(self):
    id = self.get("id", None)
    if id is None:
        id = _get_global_lib_id()
        self["id"] = id
        _inc_global_lib_id(id)

    return id


def _create_value_key(name):
    return name + "_id"


def create_getter(value_key):
    """ this getter for IDProperty handles resolving the lookup from unique id
    to object name.  we also take into account the special values of None
    (meaning the id was never set or has been unset), and -1 (meaning the
    reference has been broken) """

    def fn(self):
        name = ""
        ob_id = self.get(value_key, None)

        # meaning our reference has been broken
        if ob_id is -1:
            name = NOT_FOUND

        elif ob_id is not None:
            ob = get_object_by_id(ob_id)
            if ob:
                name = ob.name
            else:
                name = NOT_FOUND
                # mark the reference as broken
                self[value_key] = -1

        return name
    return fn


def create_setter(value_key, validator=None):
    """ this setter for IDProperty handles taking an object name, determining if
    it points to a valid object, then setting our property to that object's
    unique id.  we also accept a validator function which returns a boolean
    representing whether or not this object is valid to be used as a reference.
    a use-case for the validator might be that you only want the object with an
    IDProperty to accept references to objects that have a red material.  your
    validator function would then check for that red material and return the
    appropriate boolean """

    def fn(self, value):
        if value == "":
            del self[value_key]

        else:
            ob = bpy.data.objects.get(value, None)
            if ob:
                valid = True
                if validator:
                    valid = validator(ob)

                if valid:
                    self[value_key] = ob.id

    return fn


def IDProperty(*args, **kwargs):
    """ the main class.  """
    value_key = _create_value_key(kwargs["name"])
    validator = kwargs.pop("validator", None)

    kwargs["get"] = create_getter(value_key)
    kwargs["set"] = create_setter(value_key, validator)

    return p.StringProperty(*args, **kwargs)
    
    

def register():
    bpy.types.Object.id = p.IntProperty(name="unique id", get=get_ob_id)
    bpy.types.Library.id = p.IntProperty(name="unique id", get=get_lib_id)
    bpy.types.Scene.ob_id_counter = p.IntProperty(name="unique id counter", default=0)
    bpy.types.Scene.lib_id_counter = p.IntProperty(name="unique id counter", default=0)


def unregister():
    del bpy.types.Object.id
    del bpy.types.Scene.ob_id_counter
    
try:
    unregister()
except:
    pass
register()

