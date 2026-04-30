"""Blender renderer for ClusPot hero cluster images.

Run: blender --background --python render_clusters.py -- <mode> <out_path>
Modes: mono (Au, M55), bi (Au+Ag, M147), hea (Au-Ag-Pt-Pd-Cu, M147).

Generates cuboctahedral magic-number FCC clusters and renders them with
Cycles using PBR metal materials and a 3-point studio light setup.
Output is a transparent-background PNG so the website's panel handles
the surrounding navy/grid backdrop.
"""
import bpy
import math
import sys
import random


# ─── Parse argv ──────────────────────────────────────────────────────
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []
mode    = argv[0] if argv else "mono"
out_png = argv[1] if len(argv) > 1 else f"/tmp/cluster-{mode}.png"


# ─── Clean default scene ─────────────────────────────────────────────
for obj   in list(bpy.data.objects):    bpy.data.objects.remove(obj, do_unlink=True)
for mesh  in list(bpy.data.meshes):     bpy.data.meshes.remove(mesh)
for mat   in list(bpy.data.materials):  bpy.data.materials.remove(mat)
for light in list(bpy.data.lights):     bpy.data.lights.remove(light)
for cam   in list(bpy.data.cameras):    bpy.data.cameras.remove(cam)


# ─── FCC cuboctahedral magic-number cluster ──────────────────────────
def cluster_atoms(n_shells, atom_r=1.0):
    """Generate atom positions of an FCC cuboctahedral M(N) cluster.
    n_shells=2 → 55 atoms (M55).  n_shells=3 → 147 atoms (M147)."""
    a_nn   = 2.0 * atom_r
    a_lat  = a_nn * math.sqrt(2)
    R_max  = n_shells * a_nn
    R2_max = R_max ** 2 + 0.001
    atoms  = []
    nm     = int(R_max / (a_lat / 2)) + 2
    for h in range(-nm, nm + 1):
        for k in range(-nm, nm + 1):
            for l in range(-nm, nm + 1):
                if (h + k + l) % 2:                continue
                x, y, z = h * a_lat/2, k * a_lat/2, l * a_lat/2
                if x*x + y*y + z*z <= R2_max:      atoms.append((x, y, z))
    return atoms


# ─── PBR metal materials ─────────────────────────────────────────────
def make_metal(name, base_color, roughness=0.2):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*base_color, 1.0)
    bsdf.inputs['Metallic'].default_value   = 1.0
    bsdf.inputs['Roughness'].default_value  = roughness
    # Anisotropic specular looks more like polished metal
    if 'Specular' in bsdf.inputs:
        bsdf.inputs['Specular'].default_value = 0.55
    return mat

mat_au = make_metal("Gold",      (1.000, 0.700, 0.250), 0.18)
mat_ag = make_metal("Silver",    (0.940, 0.940, 0.920), 0.16)
mat_cu = make_metal("Copper",    (0.955, 0.580, 0.430), 0.20)
mat_pt = make_metal("Platinum",  (0.820, 0.810, 0.770), 0.22)
mat_pd = make_metal("Palladium", (0.700, 0.680, 0.650), 0.26)


# ─── Composition by mode ─────────────────────────────────────────────
if mode == "mono":
    atoms = cluster_atoms(n_shells=2)                    # M55
    mats  = [mat_au] * len(atoms)
elif mode == "bi":
    atoms = cluster_atoms(n_shells=3)                    # M147
    rng = random.Random(42)
    mats = [rng.choice([mat_au, mat_ag]) for _ in atoms]
elif mode == "hea":
    atoms = cluster_atoms(n_shells=3)                    # M147
    rng = random.Random(7)
    pool = [mat_au, mat_ag, mat_pt, mat_pd, mat_cu]
    mats = [rng.choice(pool) for _ in atoms]
else:
    raise SystemExit(f"unknown mode: {mode!r}")
print(f"[render] mode={mode}  atoms={len(atoms)}")


# ─── Place atoms ────────────────────────────────────────────────────
# Build a single low-poly sphere mesh, then instance it for every atom
# (much faster than calling primitive_uv_sphere_add 147 times).
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=48, ring_count=24)
template = bpy.context.object
template.name = "atom_template"
bpy.ops.object.shade_smooth()
template.hide_render = True

for i, ((x, y, z), mat) in enumerate(zip(atoms, mats)):
    obj = template.copy()
    obj.data = template.data            # share mesh data
    obj.location = (x, y, z)
    obj.name = f"atom_{i:03d}"
    obj.hide_render = False
    obj.data = template.data.copy()     # need own data to assign material
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    bpy.context.collection.objects.link(obj)


# ─── Tilt the cluster a touch so we see facets, not a flat ring ──────
bpy.ops.object.empty_add(location=(0, 0, 0))
pivot = bpy.context.object
pivot.name = "cluster_pivot"
# Look down a (111) axis so triangular facets are dominant — more
# spherical-looking than the (100) square-face view.
pivot.rotation_euler = (math.radians(35), math.radians(45), math.radians(35))
for obj in bpy.data.objects:
    if obj.name.startswith("atom_") and obj.name != "atom_template":
        obj.parent = pivot


# ─── 3-point studio lighting ────────────────────────────────────────
def add_area_light(loc, rot, energy, size=5.0):
    bpy.ops.object.light_add(type='AREA', location=loc)
    L = bpy.context.object
    L.data.energy = energy
    L.data.size   = size
    L.rotation_euler = rot
    return L

# Key light — bright, upper-left, slightly in front
add_area_light(loc=(-9, -9, 11),
               rot=(math.radians(40), 0, math.radians(-42)),
               energy=8000, size=6)
# Fill — right side, softer
add_area_light(loc=(8, -3, 4),
               rot=(math.radians(58), 0, math.radians(72)),
               energy=2200, size=5)
# Rim — back, picks out silhouette
add_area_light(loc=(0, 9, 7),
               rot=(math.radians(-55), 0, math.radians(180)),
               energy=3500, size=5)
# Top fill — diffuse from above so the upper hemisphere isn't black
add_area_light(loc=(0, 0, 14),
               rot=(0, 0, 0),
               energy=800, size=10)


# ─── Camera ─────────────────────────────────────────────────────────
n_shells   = 2 if mode == "mono" else 3
R_cluster  = n_shells * 2.0 + 1.0          # bounding-sphere radius
cam_dist   = R_cluster * 4.5
cam_height = R_cluster * 0.7

bpy.ops.object.camera_add(location=(0, -cam_dist, cam_height))
cam = bpy.context.object
cam.data.lens = 85                          # slight telephoto, less distortion

target = bpy.data.objects.new("CamTarget", None)
bpy.context.scene.collection.objects.link(target)
constr = cam.constraints.new('TRACK_TO')
constr.target = target
constr.track_axis = 'TRACK_NEGATIVE_Z'
constr.up_axis    = 'UP_Y'

bpy.context.scene.camera = cam


# ─── World (only seen in metal reflections — film is transparent) ───
world = bpy.context.scene.world or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
nodes, links = world.node_tree.nodes, world.node_tree.links
nodes.clear()

bg_node = nodes.new('ShaderNodeBackground'); bg_node.location = (200, 0)
out_node = nodes.new('ShaderNodeOutputWorld'); out_node.location = (400, 0)

# Vertical gradient: brighter cool tone above, darker navy below — gives
# the metal a believable horizon line in its reflections.
tex_coord = nodes.new('ShaderNodeTexCoord'); tex_coord.location = (-600, 0)
mapping   = nodes.new('ShaderNodeMapping');  mapping.location   = (-400, 0)
gradient  = nodes.new('ShaderNodeTexGradient')
gradient.gradient_type = 'EASING'; gradient.location = (-200, 0)
ramp      = nodes.new('ShaderNodeValToRGB'); ramp.location = (0, 0)

links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])
links.new(mapping.outputs['Vector'],      gradient.inputs['Vector'])
links.new(gradient.outputs['Color'],      ramp.inputs['Fac'])
links.new(ramp.outputs['Color'],          bg_node.inputs[0])
links.new(bg_node.outputs['Background'],  out_node.inputs['Surface'])

ramp.color_ramp.elements[0].color = (0.020, 0.030, 0.055, 1)   # bottom
ramp.color_ramp.elements[1].color = (0.140, 0.180, 0.250, 1)   # top — modest sky tint, lights do the work
bg_node.inputs[1].default_value = 1.0


# ─── Render settings ────────────────────────────────────────────────
scene = bpy.context.scene
scene.render.engine                     = 'CYCLES'
scene.cycles.samples                    = 192
scene.cycles.use_denoising              = True
scene.render.resolution_x               = 1024
scene.render.resolution_y               = 1024
scene.render.film_transparent           = True
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode  = 'RGBA'
scene.view_settings.view_transform      = 'Standard'
scene.view_settings.look                = 'High Contrast'
scene.view_settings.exposure            = 0.5

# Try GPU; silently fall back to CPU if no device
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for backend in ('CUDA', 'OPTIX', 'HIP', 'METAL'):
        prefs.compute_device_type = backend
        prefs.get_devices()
        if any(d.type != 'CPU' for d in prefs.devices):
            scene.cycles.device = 'GPU'
            for d in prefs.devices:
                d.use = (d.type != 'CPU')
            print(f"[render] GPU backend: {backend}")
            break
    else:
        print("[render] no GPU detected — CPU render")
except Exception as e:
    print(f"[render] GPU init failed ({e}) — CPU render")


# ─── Render! ────────────────────────────────────────────────────────
scene.render.filepath = out_png
bpy.ops.render.render(write_still=True)
print(f"[render] saved {out_png}")
