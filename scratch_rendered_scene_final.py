import sys
sys.path.insert(0, r'C:\PROJECTS\newmanim')
from manim import *
from app.craft_library import CraftContext, introduce_concept, transform_equation, compare_side_by_side, plot_math_curve_with_tangent_and_area

class CraftScene_29bd35a2_bb1f_48aa_a063_8f99d3a73dc7(Scene):
    def construct(self):
        ctx = CraftContext(self, orientation='portrait')

        # Beat 1 - INTRODUCE_CONCEPT
        introduce_concept(ctx, title='Start with the function', text='Work on f(x)=x^3-3x^2+4 over [-2,3], with x=2 marked on the axis.')

        # Beat 2 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='f(x)=x^3-3x^2+4', new_eq="f'(x)=3x^2-6x=3x(x-2)", heading='Differentiate to find critical points')

        # Beat 3 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq="f''(x)=6x-6", new_eq="f''(2)=6>0\\Rightarrow \\text{local minimum at }(2,0)", heading='Use the second derivative test')

        # Beat 4 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='(2,0)', new_eq='y=0', heading='Find the tangent line at the minimum')

        # Beat 5 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='f(x)=x^3-3x^2+4', new_eq='(x-2)^2(x+1)=0\\Rightarrow P=(-1,0)', heading='Solve for the second intersection')

        # Beat 6 - PLOT_MATH_CURVE
        plot_math_curve_with_tangent_and_area(ctx, heading='Area between the curve and tangent line')

        # Beat 7 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='A=\\int_{-1}^{2}(x^3-3x^2+4)\\,dx', new_eq='A=\\left[\\frac{x^4}{4}-x^3+4x\\right]_{-1}^{2}=\\frac{27}{4}', heading='Compute the definite integral')

        # Beat 8 - PLOT_MATH_CURVE
        plot_math_curve_with_tangent_and_area(ctx, heading='Inscribed circle from the tangent line')

        # Beat 9 - TRANSFORM_EQUATION
        transform_equation(ctx, old_eq='|4-r|=r', new_eq='r=2', heading='Solve for the circle radius')

        # Beat 10 - NONE
        # Gap: No matching craft template for Beat 10
        self.wait(3.0)
