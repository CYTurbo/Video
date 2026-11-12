"""Blender: 3D extruded title + keyframed camera orbit + area lights + emission accent ring.

Run with either:
  blender --background --factory-startup --python title3d.py -- args.json
  python (venv with bpy) title3d.py -- args.json
"""
import json
import math
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
A = json.load(open(argv[0])) if argv else {}
TEXT = A.get("text", "AI VIDEO STUDIO")
OUT = A.get("out_dir", "/tmp/title3d")
W, H, FPS, N = A.get("width", 1920), A.get("height", 1080), A.get("fps", 30), A.get("frames", 120)
ENGINE = A.get("engine", "CYCLES")
COLOR = tuple(A.get("color", (1.0, 0.45, 0.1)))
BG = tuple(A.get("bg", (0.02, 0.02, 0.05)))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.resolution_percentage = int(A.get("percent", 100))
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, N
try:
    scene.render.engine = ENGINE
except TypeError:
    scene.render.engine = "CYCLES"
if scene.render.engine == "CYCLES":
    scene.cycles.device = "CPU"
    scene.cycles.samples = A.get("samples", 16)
    scene.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev_type in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
            try:
                prefs.compute_device_type = dev_type
                prefs.get_devices()
                if any(d.type == dev_type for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = True
                    scene.cycles.device = "GPU"
                    break
            except TypeError:
                continue
    except Exception:
        pass
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"

# World
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bgn = world.node_tree.nodes.get("Background")
bgn.inputs[0].default_value = (*BG, 1)
bgn.inputs[1].default_value = 1.0

# Text
bpy.ops.object.text_add(location=(0, 0, 0))
txt = bpy.context.object
txt.data.body = TEXT
txt.data.align_x = "CENTER"
txt.data.align_y = "CENTER"
txt.data.extrude = 0.12
txt.data.bevel_depth = 0.02
txt.data.bevel_resolution = 3
txt.data.size = 1.0
txt.rotation_euler = (math.radians(90), 0, 0)
mat = bpy.data.materials.new("TitleMat")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
bsdf.inputs["Base Color"].default_value = (*COLOR, 1)
bsdf.inputs["Metallic"].default_value = 0.7
bsdf.inputs["Roughness"].default_value = 0.25
txt.data.materials.append(mat)
# fit text width to ~6 units
bpy.context.view_layer.update()
dims = txt.dimensions
scale = 6.0 / max(dims.x, 1e-3)
txt.scale = (scale, scale, scale)

# Emissive ring behind the title
bpy.ops.mesh.primitive_torus_add(major_radius=3.6, minor_radius=0.04, location=(0, 1.5, 0), rotation=(math.radians(90), 0, 0))
ring = bpy.context.object
em = bpy.data.materials.new("Glow")
em.use_nodes = True
nt = em.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
e = nt.nodes.new("ShaderNodeEmission")
e.inputs[0].default_value = (0.2, 0.8, 1.0, 1)
e.inputs[1].default_value = 6.0
o = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(e.outputs[0], o.inputs[0])
ring.data.materials.append(em)
ring.rotation_mode = "XYZ"
ring.keyframe_insert("rotation_euler", frame=1)
ring.rotation_euler[1] = math.radians(180)
ring.keyframe_insert("rotation_euler", frame=N)

# Floor (reflective)
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, -1.2))
floor = bpy.context.object
fm = bpy.data.materials.new("Floor")
fm.use_nodes = True
fb = fm.node_tree.nodes.get("Principled BSDF")
fb.inputs["Base Color"].default_value = (0.02, 0.02, 0.03, 1)
fb.inputs["Roughness"].default_value = 0.15
floor.data.materials.append(fm)

# Lights (aimed at the title with Track-To constraints)
bpy.ops.object.empty_add(location=(0, 0, 0))
target = bpy.context.object
for loc, energy, col in [((-4, -5, 4), 1500, (1, 0.85, 0.7)), ((5, -4, 1.5), 1000, (0.4, 0.7, 1)), ((0, 4, 4), 900, (1, 0.4, 0.8))]:
    bpy.ops.object.light_add(type="AREA", location=loc)
    L = bpy.context.object
    L.data.energy = energy
    L.data.size = 3
    L.data.color = col
    c = L.constraints.new("TRACK_TO")
    c.target = target
    c.track_axis = "TRACK_NEGATIVE_Z"
    c.up_axis = "UP_Y"

# Camera: orbit + dolly with eased keyframes, tracking the title
bpy.ops.object.camera_add()
cam = bpy.context.object
scene.camera = cam
cam.data.lens = 35
tc = cam.constraints.new("TRACK_TO")
tc.target = target
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"
cam.data.dof.use_dof = True
cam.data.dof.focus_object = target
cam.data.dof.aperture_fstop = 2.8
keys = [(1, -55, 16, 3.2), (int(N * 0.45), -12, 11, 1.2), (int(N * 0.8), 8, 9.5, 0.6), (N, 14, 9.0, 0.5)]
for f, ang, dist, z in keys:
    a = math.radians(ang)
    cam.location = (dist * math.sin(a), -dist * math.cos(a), z)
    cam.keyframe_insert("location", frame=f)
# Bezier ease on all camera keys
anim = cam.animation_data
if anim and anim.action:
    try:
        curves = anim.action.fcurves
    except AttributeError:  # Blender 5 layered actions
        curves = [fc for layer in anim.action.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            kp.easing = "EASE_IN_OUT"
# Motion blur
scene.render.use_motion_blur = True
scene.render.motion_blur_shutter = 0.5

scene.render.filepath = OUT.rstrip("/\\") + "/frame_"
bpy.ops.render.render(animation=True)
print("TITLE3D_DONE", N, "frames ->", OUT)
