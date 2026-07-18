import sys
sys.path.insert(0, r'C:\PROJECTS\newmanim')
from manim import *
from app.craft_library import CraftContext, introduce_concept, transform_equation, compare_side_by_side, plot_math_curve_with_tangent_and_area

class CraftScene_d33c819e_7bb8_42e1_b355_2d753c10359f(Scene):
    def construct(self):
        ctx = CraftContext(self, orientation='portrait')

        # Beat 1 - PLOT_MATH_CURVE
        plot_math_curve_with_tangent_and_area(ctx, heading='Graph the Cubic')

        # Beat 2 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='f(x)=x^3-3x^2+4', new_eq="f'(x)=3x^2-6x=3x(x-2)", heading='Differentiate and Factor')

        # Beat 3 - COMPARE_SIDE_BY_SIDE
        compare_side_by_side(ctx, left_text="Solve f'(x)=0 to find critical x-values", left_eq='3x(x-2)=0 \\Rightarrow x=0,2', right_text="Check the sign of f'(x) to locate the local minimum", right_eq="f'(x)<0 \\text{ on } (0,2),\\quad f'(x)>0 \\text{ on } (2,\\infty)", heading='Critical Points and Sign Change')

        # Beat 4 - PLOT_MATH_CURVE
        plot_math_curve_with_tangent_and_area(ctx, heading='Tangent Line and Second Intersection')

        # Beat 5 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='x^3-3x^2+4=0', new_eq='(x-2)^2(x+1)=0', heading='Solve for the Enclosed Region')

        # Beat 6 - COMPARE_SIDE_BY_SIDE
        compare_side_by_side(ctx, left_text='Set up the definite integral over the bounded interval', left_eq='A=\\int_{-1}^{2}(x^3-3x^2+4)\\,dx', right_text='Evaluate using the antiderivative', right_eq='\\left[\\frac{x^4}{4}-x^3+4x\\right]_{-1}^{2}=\\frac{27}{4}', heading='Area of the Shaded Region')

        # Beat 7 - PLOT_MATH_CURVE
        plot_math_curve_with_tangent_and_area(ctx, heading='Locate the Maximum and Inscribed Circle')

        # Beat 8 - COMPARE_SIDE_BY_SIDE
        compare_side_by_side(ctx, left_text='Second intersection and area', left_eq='P=(-1,0),\\quad A=\\frac{27}{4}', right_text='Circle radius', right_eq='r=2', heading='Final Results')
