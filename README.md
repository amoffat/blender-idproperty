# Usage

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
