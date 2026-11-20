"""
plot_region.py - Draw and check the teleoperation working region BEFORE using it on the robot.

HOW THE REGION IS BUILT (same rules as Teleop_Region.erp)
    step 1  ELLIPSOID   is the point inside the ellipsoid?
    step 2  BOX         is the point inside the box?
    step 3  INTERSECTION region = ellipsoid AND box        (a point must be in BOTH shapes)
    step 4  TOLERANCE   steps 1-3 are done twice: exact shapes, and shapes grown by TOL mm.
                        Inside the grown shapes only = allowed, but logged as "TOL BAND".
    step 5  HARD LIMITS table, near the base, arm too stretched, wrist too close.
                        They CUT AWAY parts of the intersection and the tolerance never relaxes them.
    final   allowed = (inside the grown intersection) AND (no hard limit broken)

    So the coloured area in the cuts is NOT simply ellipsoid + box: the hard limits remove the
    hole around the base (NEAR BASE), the outer part the arm cannot reach (TOO FAR) and
    everything below the table (TABLE). The dashed lines show the ellipsoid and the box alone.

HOW TO TUNE (change the same number here and in Teleop_Region.erp)
    want to go farther left/right near the table -> make the BOX wider (BOX_MIN/BOX_MAX y)
    want to go higher                            -> raise ELL_CENTRE z or ELL_SEMI z
    want more slack at every border              -> TOL
    robot stops by itself near full reach        -> lower REACH_MAX
    tool hits the table                          -> raise Z_FLOOR
    Run this script after every change: dark green = allowed, light green = tolerance band,
    orange = outside ellipsoid and box, red = hard limit. Your POINTS must be dark green.

ARM GEOMETRY (ER4-550 operation manual, Figure 3-3)
    J2 is 350 mm above the base, upper arm 260 mm, forearm 25 mm offset + 294 mm to the wrist
    centre P (295 mm), P is between R147 and R555 from J2, P to flange 80.3 mm, our tool 90 mm
    along the tool z axis. With the tool pointing down P is 80.3 + 90 = 170.3 mm above the TCP.

Usage (walter venv):   python plot_region.py
"""

import math

import matplotlib.pyplot as plt
import numpy as np

# ==== SETTINGS (same values as Teleop_Region.erp) ========================================
ELL_CENTRE = (300.0, 0.0, 310.0)        # R_EX_CX, R_EX_CY, R_EX_CZ
ELL_SEMI = (375.0, 350.0, 500.0)       # R_EX_AX, R_EX_AY, R_EX_AZ  (half of 800, 500, 500)
BOX_MIN = (150.0, -270.0, 30.0)        # R_BX_XMIN, R_BX_YMIN, R_BX_ZMIN
BOX_MAX = (550.0, 270.0, 650.0)        # R_BX_XMAX, R_BX_YMAX, R_BX_ZMAX
TOL = 30.0                             # R_TOL       extra margin around ellipsoid and box
Z_FLOOR = 30.0                         # R_Z_FLOOR   lowest TCP z (table)
BASE_R = 150.0                         # R_BASE_R    min horizontal distance TCP - J1 axis
#                                        manual: base body reaches 136 mm from J1 axis (Fig 3-3)
#                                        -> BASE_R = 136 + half gripper width + safety margin
REACH_MAX = 750.0                      # R_REACH_MAX max wrist centre - J2 (robot limit 555)
REACH_MIN = 212.0                      # R_REACH_MIN min wrist centre - J2 (robot limit 147)
J2_Z = 350.0                           # R_J2_Z      shoulder height
FLANGE = 80.3                          # wrist centre P -> J6 flange
TOOL_LEN = 90.0                        # our tool, along the tool z axis
WRIST_UP = FLANGE + TOOL_LEN           # R_WRIST_UP  = 170.3

HOME = (274.31, 14.38, 230.69, -177.99, -0.68, 177.34)   # t_g.pose_home: x y z A B C
POINTS = {                             # points you need to reach (x, y, z)
    "home": HOME[:3],
    "PRESA_1": (443.2, 48.1, 47.5), "PRESA_3": (443.1, 129.1, 51.8),
    "PRESA_4": (482.7, 129.1, 48.6), "PRESA_6": (482.7, 47.9, 50.4),
    "FORO_1": (440.2, -31.5, 48.8), "FORO_3": (443.5, -113.8, 49.4),
    "FORO_4": (483.7, -113.6, 48.8), "FORO_6": (483.0, -32.2, 47.8),
}
# CAGE (black): the physical cell the robot works in. Its lower face is the work table (z = 0).
TABLE_CENTRE = (235.0, 0.0, 0.0)       # centre of the table = centre of the cage floor, in ROBOT
#                                        BASE coordinates (mm). If the pick points come out
#                                        "outside cage", the sign is wrong: try (-235, 0, 0).
CAGE_SIZE = (730.0, 620.0, 900.0)    # length (along x), width (along y), height (along z)

# The 3D region is shown as flat SLICES (like a CT scan). Each slice keeps one coordinate fixed:
CUT_HEIGHTS = (30.0, 600.0)          # TOP views   (z fixed): table/pick height and home height
CUT_Y = 0.0                            # SIDE view   (y fixed): vertical plane through the base
CUT_X = 450.0                          # FRONT view  (x fixed): vertical plane through the pick area
# =========================================================================================

# Cage corners computed from the settings above (min and max of x, y, z)
CAGE_MIN = (TABLE_CENTRE[0] - CAGE_SIZE[0] / 2, TABLE_CENTRE[1] - CAGE_SIZE[1] / 2, TABLE_CENTRE[2])
CAGE_MAX = (TABLE_CENTRE[0] + CAGE_SIZE[0] / 2, TABLE_CENTRE[1] + CAGE_SIZE[1] / 2,
            TABLE_CENTRE[2] + CAGE_SIZE[2])
# Plot area = cage plus 100 mm on every side
XLIM = (CAGE_MIN[0] - 100, CAGE_MAX[0] + 100)
YLIM = (CAGE_MIN[1] - 100, CAGE_MAX[1] + 100)
ZLIM = (CAGE_MIN[2] - 100, CAGE_MAX[2] + 100)


# ---- step 1: ellipsoid ------------------------------------------------------------------
def in_ellipsoid(x, y, z, margin):
    """Inside when (dx/ax)^2 + (dy/ay)^2 + (dz/az)^2 <= 1. margin grows every semi-axis."""
    (cx, cy, cz), (ax, ay, az) = ELL_CENTRE, ELL_SEMI
    s = ((x - cx) / (ax + margin)) ** 2 + ((y - cy) / (ay + margin)) ** 2 \
        + ((z - cz) / (az + margin)) ** 2
    return s <= 1.0


# ---- step 2: box ------------------------------------------------------------------------
def in_box(x, y, z, margin):
    """Inside when every coordinate is between its min and max. margin moves every side out."""
    return (BOX_MIN[0] - margin <= x <= BOX_MAX[0] + margin and
            BOX_MIN[1] - margin <= y <= BOX_MAX[1] + margin and
            BOX_MIN[2] - margin <= z <= BOX_MAX[2] + margin)


# ---- step 3: INTERSECTION ---------------------------------------------------------------
def in_region(x, y, z, margin):
    """THE WORKING REGION: a point is good only if it is in the ellipsoid AND in the box."""
    return in_ellipsoid(x, y, z, margin) and in_box(x, y, z, margin)


# ---- step 5: hard limits ----------------------------------------------------------------
def hard_limit(x, y, z):
    """Name of the broken hard limit, or '' if none. Same order as the .erp (last one wins)."""
    reason = ""
    r2 = x * x + y * y                              # horizontal distance from J1 axis, squared
    if r2 < BASE_R ** 2:
        reason = "NEAR BASE"
    d2 = r2 + (z + WRIST_UP - J2_Z) ** 2            # wrist centre to J2, squared
    if d2 > REACH_MAX ** 2:
        reason = "TOO FAR"
    if d2 < REACH_MIN ** 2:
        reason = "WRIST CLOSE"
    if z < Z_FLOOR:
        reason = "TABLE"
    return reason


# ---- cage (drawing and printout only, not used by the robot program yet) -----------------
def in_cage(x, y, z):
    """True if the point is inside the black cage."""
    return (CAGE_MIN[0] <= x <= CAGE_MAX[0] and CAGE_MIN[1] <= y <= CAGE_MAX[1]
            and CAGE_MIN[2] <= z <= CAGE_MAX[2])


# ---- final decision ---------------------------------------------------------------------
def check(x, y, z):
    """'ALLOWED', 'TOL BAND' (allowed), 'OUT REGION' or the hard limit name (refused)."""
    hard = hard_limit(x, y, z)
    if hard:
        return hard
    if in_region(x, y, z, 0.0):                    # exact intersection
        return "ALLOWED"
    if in_region(x, y, z, TOL):                    # intersection of the shapes grown by TOL (step 4)
        return "TOL BAND"
    return "OUT REGION"


# ---- drawing helpers --------------------------------------------------------------------
COLORS = {"ALLOWED": 3, "TOL BAND": 2, "OUT REGION": 1}          # everything else = hard (0)
CMAP = plt.matplotlib.colors.ListedColormap(["#e8a0a0", "#f5c98b", "#b7e4b7", "#3a9d3a"])


def rot_zyx(a, b, c):
    """Estun A, B, C in degrees: A about z, then B about y', then C about x''."""
    a, b, c = np.radians([a, b, c])
    rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    rx = np.array([[1, 0, 0], [0, math.cos(c), -math.sin(c)], [0, math.sin(c), math.cos(c)]])
    return rz @ ry @ rx


def arm_at_home(rot):
    """Stick model base - J2 - J3 - P - flange - TCP (2-link inverse kinematics, elbow up)."""
    tcp = np.array(HOME[:3])
    flange = tcp - rot[:, 2] * TOOL_LEN
    p = flange - rot[:, 2] * FLANGE
    j2 = np.array([0.0, 0.0, J2_Z])
    phi = math.atan2(p[1], p[0])
    r, h = math.hypot(p[0], p[1]), p[2] - J2_Z
    l1, l2 = 260.0, math.hypot(294.0, 25.0)
    d = math.hypot(r, h)
    ang = math.atan2(h, r) + math.acos((l1 ** 2 + d ** 2 - l2 ** 2) / (2 * l1 * d))
    j3 = j2 + l1 * np.array([math.cos(ang) * math.cos(phi), math.cos(ang) * math.sin(phi),
                             math.sin(ang)])
    return np.array([[0, 0, 0], j2, j3, p, flange, tcp])


def draw_cut(ax, xs, ys, point_of, title):
    """Colour every grid cell with the result of check()."""
    img = [[COLORS.get(check(*point_of(a, b)), 0) for a in xs] for b in ys]
    ax.imshow(img, origin="lower", cmap=CMAP, vmin=0, vmax=3,
              extent=(xs[0], xs[-1], ys[0], ys[-1]))
    ax.set_title(title, fontsize=10)


def ellipse_section(ax, k, cut, i, j):
    """Dashed outline of the ellipsoid cut by the plane (coordinate k = cut), axes i, j."""
    f = 1 - ((cut - ELL_CENTRE[k]) / ELL_SEMI[k]) ** 2
    if f > 0:
        t = np.linspace(0, 2 * np.pi, 100)
        ax.plot(ELL_CENTRE[i] + ELL_SEMI[i] * math.sqrt(f) * np.cos(t),
                ELL_CENTRE[j] + ELL_SEMI[j] * math.sqrt(f) * np.sin(t), "g--", lw=1)


def box_section(ax, bmin, bmax, k, cut, i, j, color, style="--"):
    """Outline of a box (bmin..bmax) cut by the plane (coordinate k = cut), drawn on axes i, j.
    k, i, j are 0 = x, 1 = y, 2 = z. Nothing is drawn if the plane misses the box."""
    if bmin[k] <= cut <= bmax[k]:
        x0, x1, y0, y1 = bmin[i], bmax[i], bmin[j], bmax[j]
        ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], style, color=color, lw=1.5)


def box_3d(ax, bmin, bmax, color, label):
    """The 12 edges of a box: pairs of corners that differ in exactly one coordinate."""
    corners = [(x, y, z) for x in (bmin[0], bmax[0]) for y in (bmin[1], bmax[1])
               for z in (bmin[2], bmax[2])]
    first = True
    for a in corners:
        for b in corners:
            if a < b and sum(p != q for p, q in zip(a, b)) == 1:
                ax.plot(*zip(a, b), color=color, label=label if first else None)
                first = False


def outlines(ax, k, cut, i, j):
    """Ellipsoid (green), region box (green) and cage (black) outlines on one slice."""
    ellipse_section(ax, k, cut, i, j)
    box_section(ax, BOX_MIN, BOX_MAX, k, cut, i, j, "g")
    box_section(ax, CAGE_MIN, CAGE_MAX, k, cut, i, j, "black", "-")


def main():
    rot = rot_zyx(*HOME[3:])
    arm = arm_at_home(rot)
    print(f"Tool z axis at home (should point down): {np.round(rot[:, 2], 2)}")
    print(f"Cage x {CAGE_MIN[0]:.0f}..{CAGE_MAX[0]:.0f}  y {CAGE_MIN[1]:.0f}..{CAGE_MAX[1]:.0f}"
          f"  z {CAGE_MIN[2]:.0f}..{CAGE_MAX[2]:.0f}  (robot base frame, mm)")
    print(f"\n{'point':10s} {'x':>7s} {'y':>7s} {'z':>7s}   {'cage':8s} region")
    for name, (x, y, z) in POINTS.items():
        cage = "inside" if in_cage(x, y, z) else "OUTSIDE"
        print(f"{name:10s} {x:7.1f} {y:7.1f} {z:7.1f}   {cage:8s} {check(x, y, z)}")

    fig = plt.figure(figsize=(13, 7))
    fig.suptitle("dark green ALLOWED | light green TOL BAND | orange OUT REGION | "
                 "red HARD LIMIT\ndashed (green): ellipsoid and box alone | black: cage")

    # 3D view
    ax = fig.add_subplot(1, 2, 1, projection="3d")
    u, v = np.meshgrid(np.linspace(0, 2 * np.pi, 40), np.linspace(0, np.pi, 20))
    ax.plot_wireframe(ELL_CENTRE[0] + ELL_SEMI[0] * np.cos(u) * np.sin(v),
                      ELL_CENTRE[1] + ELL_SEMI[1] * np.sin(u) * np.sin(v),
                      ELL_CENTRE[2] + ELL_SEMI[2] * np.cos(v), color="g", alpha=0.2, lw=0.6)
    box_3d(ax, BOX_MIN, BOX_MAX, color="g", label=None)
    box_3d(ax, CAGE_MIN, CAGE_MAX, "black", "cage")
    tx, ty = np.meshgrid([CAGE_MIN[0], CAGE_MAX[0]], [CAGE_MIN[1], CAGE_MAX[1]])
    ax.plot_surface(tx, ty, np.full(tx.shape, Z_FLOOR), color="grey", alpha=0.15)
    ax.plot(*arm.T, "-o", color="black", lw=3, label="arm at home")
    for origin, r, length, label in (((0, 0, 0), np.eye(3), 120, "base"),
                                     (HOME[:3], rot, 80, "tool")):
        for k, c in enumerate("rgb"):               # x red, y green, z blue
            ax.quiver(*origin, *(r[:, k] * length), color=c, lw=2)
        ax.text(*origin, "  " + label)
    for x, y, z in POINTS.values():
        ax.scatter(x, y, z, color="black", s=15)
    ax.set_xlabel("x"), ax.set_ylabel("y"), ax.set_zlabel("z")
    ax.set_xlim(XLIM), ax.set_ylim(YLIM), ax.set_zlim(ZLIM)
    ax.legend(loc="upper left")

    # slices: top views (x right, y up), side view (x right, z up), front view (y right, z up)
    xs, ys, zs = np.linspace(*XLIM, 181), np.linspace(*YLIM, 141), np.linspace(*ZLIM, 151)
    for n, zc in enumerate(CUT_HEIGHTS):
        axc = fig.add_subplot(2, 4, 3 + n)
        draw_cut(axc, xs, ys, lambda a, b: (a, b, zc), f"TOP view, slice at z = {zc:.0f}")
        outlines(axc, 2, zc, 0, 1)
        for x, y, z in POINTS.values():
            if abs(z - zc) < 40:
                axc.plot(x, y, "k.")
        axc.plot(0, 0, "k+", ms=12)
    axs = fig.add_subplot(2, 4, 7)
    draw_cut(axs, xs, zs, lambda a, b: (a, CUT_Y, b), f"SIDE view, slice at y = {CUT_Y:.0f}")
    outlines(axs, 1, CUT_Y, 0, 2)
    axs.plot(arm[:, 0], arm[:, 2], "-o", color="black")
    for x, y, z in POINTS.values():
        axs.plot(x, z, "k.")
    axf = fig.add_subplot(2, 4, 8)
    draw_cut(axf, ys, zs, lambda a, b: (CUT_X, a, b), f"FRONT view, slice at x = {CUT_X:.0f}")
    outlines(axf, 0, CUT_X, 1, 2)
    for x, y, z in POINTS.values():
        if abs(x - CUT_X) < 50:
            axf.plot(y, z, "k.")
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
