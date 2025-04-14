from spectroscopy_bluesky.i18.config_server.perp_converter import (
    BraggAngleToDistancePerpConverter,
)

## Test evaluator
config_root = "/scratch/gda/9.master-6March-test-newconfig/workspace_git/gda-diamond.git/configurations/i18-config"  # noqa: E501
filename = f"{config_root}/lookupTables/Si111/Deg_dcm_perp_mm_converter.xml"

converter = BraggAngleToDistancePerpConverter.create_from_file(filename)
for angle in range(10, 20):
    distance = converter.bragg_angle_degrees_to_distance(angle)
    print(f"for angle {angle} there is distance: {distance}")
    # todo write the test
