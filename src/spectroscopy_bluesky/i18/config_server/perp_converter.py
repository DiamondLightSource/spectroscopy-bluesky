import math
import re
from pathlib import Path


class BraggAngleToDistancePerpConverter:
    constant_top = 12.82991823
    constant_subtract = -0.33493688
    constant_inverse = 12.489

    def __init__(
        self, constant_top: float, constant_subtract: float, constant_inverse: float
    ):
        self.constant_top = constant_top
        self.constant_subtract = constant_subtract
        self.constant_inverse = constant_inverse

    def bragg_angle_degrees_to_distance(self, angle: float) -> float:
        return (self.constant_top / math.cos(angle / math.pi)) - self.constant_subtract

    def distance_mm_to_bragg_angle_degrees(self, distance: float) -> float:
        return self.constant_inverse / distance

    @staticmethod
    def create_from_file(path: Path) -> "BraggAngleToDistancePerpConverter":
        with open(path) as f:
            content = f.read()

        # Extract constants from ExpressionStoT
        sto_t_match = re.search(
            r"<ExpressionStoT>(\d+\.\d+)/cos\(X/.*?\)-(\d+\.\d+)</ExpressionStoT>",
            content,
        )
        if not sto_t_match:
            raise ValueError("Failed to parse <ExpressionStoT> from file")

        constant_top = float(sto_t_match.group(1))
        constant_subtract = float(sto_t_match.group(2))

        # Extract constant from ExpressionTtoS
        t_to_s_match = re.search(
            r"<ExpressionTtoS>(\d+\.\d+)/X</ExpressionTtoS>",
            content,
        )
        if not t_to_s_match:
            raise ValueError("Failed to parse <ExpressionTtoS> from file")

        constant_inverse = float(t_to_s_match.group(1))

        return BraggAngleToDistancePerpConverter(
            constant_top, constant_subtract, constant_inverse
        )


# /scratch/gda/9.master-6March-test-newconfig/workspace_git/gda-diamond.git/configurations/i18-config/lookupTables/Si111/Deg_dcm_perp_mm_converter.xml  # noqa: E501
# <JEPQuantityConverter>
# <ExpressionStoT>12.82991823/cos(X/(180/(4.0*atan(1.0))))-0.33493688</ExpressionStoT>
# <ExpressionTtoS>12.489/X</ExpressionTtoS>
# <AcceptableSourceUnits>Deg</AcceptableSourceUnits>
# <AcceptableTargetUnits>mm</AcceptableTargetUnits>
# <SourceMinIsTargetMax>false</SourceMinIsTargetMax>
# </JEPQuantityConverter>
