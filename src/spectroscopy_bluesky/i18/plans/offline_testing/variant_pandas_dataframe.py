from spectroscopy_bluesky.i18.plans.lookup_tables import load_fit_results

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
