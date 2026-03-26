import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import uuid
from pathlib import Path

import sympy as s
from sympy import sympify, symbols
from sympy import (sin, cos, tan, asin, acos, atan, atan2,
                   sinh, cosh, tanh, exp, log, sqrt, Abs,
                   sign, ceiling, floor, Rational, pi, E)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://connorfitz10.github.io"],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

# ── safe sympify namespace ────────────────────────────────────────────────────
t = symbols("t")

SAFE_NS: dict = {
    "t": t, "pi": pi, "E": E,
    "sin": sin, "cos": cos, "tan": tan,
    "asin": asin, "acos": acos, "atan": atan, "atan2": atan2,
    "sinh": sinh, "cosh": cosh, "tanh": tanh,
    "exp": exp, "log": log, "sqrt": sqrt,
    "Abs": Abs, "sign": sign, "ceiling": ceiling, "floor": floor,
    "Rational": Rational,
    "__builtins__": {},      # block all builtins
}

SAFE_RE = re.compile(r"^[\w\s\+\-\*\/\(\)\.\,\^\*]+$")


class CurveRequest(BaseModel):
    components: list[str]   # exactly 3 SymPy expression strings


def parse_curve(components: list[str]) -> s.Matrix:
    if len(components) != 3:
        raise HTTPException(422, "Exactly 3 components required.")
    parsed = []
    for comp in components:
        if not SAFE_RE.match(comp):
            raise HTTPException(422, f"Invalid characters in: {comp!r}")
        try:
            expr = sympify(comp, locals=SAFE_NS, evaluate=True)
        except Exception as exc:
            raise HTTPException(422, f"Cannot parse '{comp}': {exc}")
        extra = expr.free_symbols - {t}
        if extra:
            raise HTTPException(422, f"Unknown symbols: {extra}")
        parsed.append(expr)
    return s.Matrix(parsed)


# ── Manim scene template ──────────────────────────────────────────────────────
SCENE_TEMPLATE = textwrap.dedent("""\
    from manim import *
    import sympy as s
    import numpy as np
    from sympy import symbols, sqrt, lambdify
    from sympy import sin, cos, tan, exp, log, pi, E

    t = symbols("t")


    def TNB_get(func):
        v_sym = func.diff(t)
        speed_sym = sqrt(v_sym.dot(v_sym))
        T_sym = v_sym / speed_sym
        dT = T_sym.diff(t)
        N_sym = dT / sqrt(dT.dot(dT))
        B_sym = T_sym.cross(N_sym)
        T = lambdify(t, T_sym, "numpy")
        N = lambdify(t, N_sym, "numpy")
        B = lambdify(t, B_sym, "numpy")
        return T, N, B


    class TNBScene(ThreeDScene):
        def construct(self):
            r_sym = s.Matrix(CURVE_PLACEHOLDER)

            axes = ThreeDAxes(x_length=12, y_length=10, z_length=8)
            self.move_camera(phi=PI / 3, theta=PI / 4)
            self.add(axes)
            self.wait()

            r_temp = lambdify(t, r_sym, "numpy")
            r_plot = lambda t: np.squeeze(r_temp(t))

            C = ParametricFunction(r_plot, t_range=[0, TAU], color=RED)
            t0 = MathTex(r"\\vec{r}(t)=", color=RED)
            T_l = MathTex(r"\\vec{T}", color=GREEN)
            N_l = MathTex(r"\\vec{N}", color=BLUE)
            B_l = MathTex(r"\\vec{B}", color=PURPLE)
            TNB_l = VGroup(T_l, N_l, B_l)

            self.add_fixed_in_frame_mobjects(t0.shift(3 * UP + 3 * RIGHT).scale(0.75))
            self.play(Create(C), run_time=5)
            self.wait()

            tracker = ValueTracker(0)
            T_f, N_f, B_f = TNB_get(r_sym)
            T = lambda t: np.squeeze(T_f(t))
            N = lambda t: np.squeeze(N_f(t))
            B = lambda t: np.squeeze(B_f(t))

            T_p = Vector(T(0), color=GREEN).shift(r_plot(0))
            T_p.add_updater(lambda m: m.become(
                Vector(T(tracker.get_value()), color=GREEN).shift(r_plot(tracker.get_value()))))
            N_p = Vector(N(0), color=BLUE).shift(r_plot(0))
            N_p.add_updater(lambda m: m.become(
                Vector(N(tracker.get_value()), color=BLUE).shift(r_plot(tracker.get_value()))))
            B_p = Vector(B(0), color=PURPLE).shift(r_plot(0))
            B_p.add_updater(lambda m: m.become(
                Vector(B(tracker.get_value()), color=PURPLE).shift(r_plot(tracker.get_value()))))

            self.add(VGroup(T_p, N_p, B_p))
            self.add_fixed_in_frame_mobjects(TNB_l.arrange(DOWN).next_to(t0, 2 * RIGHT))
            self.wait()
            self.play(tracker.animate.set_value(TAU), run_time=10, rate_func=linear)
            self.wait()
""")


@app.post("/render")
async def render(req: CurveRequest):
    matrix = parse_curve(req.components)

    # Use SymPy's own str() output — safe and round-trips correctly
    matrix_repr = str([str(expr) for expr in matrix])

    work_dir = Path(tempfile.mkdtemp(prefix="tnb_"))
    scene_file = work_dir / "scene.py"
    try:
        scene_src = SCENE_TEMPLATE.replace("CURVE_PLACEHOLDER", matrix_repr)
        scene_file.write_text(scene_src, encoding="utf-8")

        result = subprocess.run(
            [
                "manim", "render",
                "-ql",                          # 480p for speed; change to -qm for HD
                "--media_dir", str(work_dir / "media"),
                str(scene_file),
                "TNBScene",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            raise HTTPException(500, f"Render failed:\n{result.stderr[-2000:]}")

        mp4_files = list((work_dir / "media").rglob("TNBScene.mp4"))
        if not mp4_files:
            raise HTTPException(500, "Output video not found.")

        video_bytes = mp4_files[0].read_bytes()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return Response(
        content=video_bytes,
        media_type="video/mp4",
        headers={"Content-Disposition": "inline; filename=tnb.mp4"},
    )
