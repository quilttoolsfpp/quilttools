import sys
sys.path.append("c:/Users/Pritt/AppData/Roaming/inkscape/extensions/quilttoolsv2.0")
import quilttools_fpp_fabric as fabric

# 1. Test pieces
pieces = [
    ([(0,0), (2,0), (2,4), (0,4)], "Main"), # 2x4 box
    ([(0,0), (5,0), (2,5)], "Accent"), # triangle
    ([(0,0), (60,0), (60,5), (0,5)], "Main"), # 60x5 box (should flag WOF if wof=41)
]

print("Testing fabric_estimate...")
results = fabric.fabric_estimate(pieces, usable_wof=41.0)
for role, est in results.items():
    print(f"Role: {role}")
    print(f"  Pieces: {est['pieces_count']}")
    print(f"  Fixed Yardage: {est['fixed_in']/36.0:.2f} yds")
    print(f"  Free Yardage: {est['free_in']/36.0:.2f} yds")
    print(f"  Exceeds WOF: {est['exceeds_wof']}")
