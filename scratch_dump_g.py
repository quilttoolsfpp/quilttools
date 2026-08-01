import xml.etree.ElementTree as ET

tree = ET.parse('antarticav1 fully correct.svg')
root = tree.getroot()

def dump_g(el, depth=0):
    tag = el.tag.split('}')[-1]
    if tag == 'g' or tag == 'svg':
        print("  " * depth + f"{tag} id={el.get('id')} label={el.get('{http://www.inkscape.org/namespaces/inkscape}label')} style={el.get('style')}")
        for child in el:
            dump_g(child, depth + 1)

dump_g(root)
