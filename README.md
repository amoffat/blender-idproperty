# About

This Blender addon aids in addon development by providing `IDProperty`, a [Property](https://www.blender.org/api/blender_python_api_2_76_release/bpy.props.html) that is able to point to another object.  Some important features:

* Provides a unique id field on all Objects, accessed by the `.id` property
* Doesn't break when the object pointed to changes its name
* Includes a convenience function for adding the property to a Panel's layout
* Automatically avoids id collisions from [linked blend files](https://www.blender.org/manual/data_system/linked_libraries.html#append-and-link)

# Basic Usage

This code sets up two IDProperties on all objects.  The first property, `some_related_object` can point to any object.  The second property, `some_camera`, will only point to Cameras.  The Panel for these properties is displayed on the Object Properties tab of the information Area.

![http://i.imgur.com/xaAy4eR.png](http://i.imgur.com/xaAy4eR.png)

```python
import bpy
from bpy.utils import register_module, unregister_module
import idproperty

class SomePanel(bpy.types.Panel):
    bl_label = "Some Properties"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    
    def draw(self, ctx):
        ob = ctx.object
        
        layout = self.layout
        row = layout.row()
        idproperty.layout_id_prop(row, ob, "some_related_object")
        
        row = layout.row()
        idproperty.layout_id_prop(row, ob, "some_camera")
        
def is_camera(ob):
    return ob.type == "CAMERA"

def register():
    bpy.types.Object.some_related_object = idproperty.IDProperty(name="something related")
    bpy.types.Object.some_camera = idproperty.IDProperty(name="some camera", validator=is_camera)
    register_module(__name__)
    
def unregister():
    del bpy.types.Object.some_related_object
    del bpy.types.Object.some_camera
    unregister_module(__name__)
    
try:
    unregister()
except:
    pass
    
register()
```

# How does it work?
