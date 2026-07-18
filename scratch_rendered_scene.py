import sys
sys.path.insert(0, r'C:\PROJECTS\newmanim')
from manim import *
from app.craft_library import CraftContext, introduce_concept, transform_equation, compare_side_by_side, plot_math_curve_with_tangent_and_area

class CraftScene_e6782e3f_e21e_4a89_a280_001e8c0a67d0(Scene):
    def construct(self):
        ctx = CraftContext(self, orientation='portrait')

        # Beat 1 - INTRODUCE_CONCEPT
        introduce_concept(ctx, title='Approach', text='Find the critical point first, use the tangent line, then solve the area and circle geometry step by step.')

        # Beat 2 - PLOT_MATH_CURVE
        plot_math_curve_with_tangent_and_area(ctx, heading='Cubic Setup')

        # Beat 3 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq="f'(x)=3x^2-6x", new_eq="f'(x)=3x(x-2)", heading='Differentiate and Factor')

        # Beat 4 - COMPARE_SIDE_BY_SIDE
        compare_side_by_side(ctx, left_text='At x=0, the function has a local maximum.', left_eq='f(0)=4', right_text='At x=2, the function has a local minimum.', right_eq='f(2)=0', heading='Critical Points and Values')

        # Beat 5 - INTRODUCE_CONCEPT
        introduce_concept(ctx, title='Tangent Line at the Minimum', text='Since the slope is zero at the local minimum, the tangent line is horizontal.')

        # Beat 6 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='\n', new_eq='y=0', heading='Tangent Line')

        # Beat 7 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='x^3-3x^2+4=0', new_eq='(x-2)^2(x+1)=0', heading='Find the Second Intersection')

        # Beat 8 - COMPARE_SIDE_BY_SIDE
        compare_side_by_side(ctx, left_text='The intersections are used as bounds for the shaded area.', left_eq='x=-1 \\text{ and } x=2', right_text='Integrate the curve above the x-axis.', right_eq='A=\\int_{-1}^{2}(x^3-3x^2+4)\\,dx', heading='Enclosed Region')

        # Beat 9 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='A=\\left[\\frac{x^4}{4}-x^3+4x\\right]_{-1}^{2}', new_eq='A=\\frac{35}{4}', heading='Area Calculation')

        # Beat 10 - INTRODUCE_CONCEPT
        introduce_concept(ctx, title='Circle Geometry', text='A circle tangent to y=0 and passing through (0,4) has center (0,2) and radius 2.')

        # Beat 11 - COMPARE_SIDE_BY_SIDE
        compare_side_by_side(ctx, left_text='Second intersection point and enclosed area.', left_eq='P=(-1,0),\\ A=\\frac{35}{4}', right_text='Circle result.', right_eq='r=2,\\ \\text{center }(0,2)', heading='Final Summary')

        # Beat 12 - PLOT_MATH_CURVE
        plot_math_curve_with_tangent_and_area(ctx, heading='Final Combined View')
