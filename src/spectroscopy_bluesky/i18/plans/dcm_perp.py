import numexpr as ne


class ExpressionEvaluator :
    def __init__(self):
        self.expression = None
        self.expression_param_name = None

    def __call__(self, value):
        return self.evalute(value)
    def evalute(self, value) :
        return ne.evaluate(self.expression, local_dict={self.expression_param_name:value}).item()

def load_dcm_perp(filename) :
    line_with_expr="ExpressionStoT"
    replacements = {"<"+line_with_expr+">":"", "</"+line_with_expr+">":"", "atan":"arctan"}

    with open(filename) as file :
        for line in file.readlines():
            if line_with_expr in line:
                func_string = line

                for k, v in replacements.items() :
                    func_string = func_string.replace(k, v)

                evaluator = ExpressionEvaluator()
                evaluator.expression = func_string
                evaluator.expression_param_name = "X"
                return evaluator

    return None

## Test evaluator
filename="/scratch/gda/9.master-6March-test-newconfig/workspace_git/gda-diamond.git/configurations/i18-config/lookupTables/Si111/Deg_dcm_perp_mm_converter.xml"

perp_for_bragg=load_dcm_perp(filename)
for angle in range(10,20) :
    print(perp_for_bragg(angle))


