import numexpr as ne

from spectroscopy_bluesky.i18.plans.curve_fitting.lookup_tables import load_fit_results


class ExpressionEvaluator:
    def __init__(self):
        self.expression = None
        self.expression_param_name = None

    def __call__(self, value):
        return self.evalute(value)

    def evalute(self, value):
        return ne.evaluate(
            self.expression, local_dict={self.expression_param_name: value}
        ).item()


def load_dcm_perp(filename):
    line_with_expr = "ExpressionStoT"
    replacements = {
        "<" + line_with_expr + ">": "",
        "</" + line_with_expr + ">": "",
        "atan": "arctan",
    }

    with open(filename) as file:
        for line in file.readlines():
            if line_with_expr in line:
                func_string = line

                for k, v in replacements.items():
                    func_string = func_string.replace(k, v)

                evaluator = ExpressionEvaluator()

                evaluator.expression = func_string
                evaluator.expression_param_name = "X"
                return evaluator

    return None


## Test evaluator
config_root = "/scratch/gda/9.master-6March-test-newconfig/workspace_git/gda-diamond.git/configurations/i18-config"  # noqa: E501
filename = f"{config_root}/lookupTables/Si111/Deg_dcm_perp_mm_converter.xml"

perp_for_bragg = load_dcm_perp(filename)
for angle in range(10, 20):
    print(perp_for_bragg(angle))  # type: ignore


filename = "lookuptable_harmonic1.txt"
# beamline_lookuptable_dir = "/dls_sw/i18/software/gda_versions/gda_9_36/workspace_git/gda-diamond.git/configurations/i18-config/lookupTables/"  # noqa: E501
# filename = beamline_lookuptable_dir + "Si111/lookuptable_harmonic9.txt"
filename = "/tmp/fits.txt"
dataframe = load_fit_results(filename)

print(dataframe)


"""
# Test updating pandas dataframe :

import pandas as pd

dataframe = pd.DataFrame({"A": ["a","b", "c", "d"],
                          "B" : [1,2,3,4]})
print(dataframe)
dataframe["B"]=[12,13,14,15] # replace some data
print(dataframe)
dataframe.drop(columns=dataframe.columns.values, inplace=True) # clear everything
print(dataframe)
dataframe.drop(dataframe.index, inplace=True) # clear everything
print(dataframe)
"""
