#!/usr/bin/env python3
import re

import inkex
import quilttools_fpp_core as core


class LabelsPlugin(inkex.Effect):
    def add_arguments(self, pars):
        pars.add_argument("--action", type=str, default="auto_label")
        pars.add_argument("--new_label", type=str, default="A1")
        pars.add_argument("--preserve_manual", type=inkex.Boolean, default=False)

    def effect(self):
        a = self.options.action
        if a == "define_section":
            self._define_section()
        elif a == "set_first":
            self._set_first_piece()
        elif a == "relabel":
            self._relabel()
        elif a == "auto_label":
            self._auto_label()
        elif a == "fix_letters":
            self._fix_letters()

    def _auto_label(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")

        block_data.tree.auto_partition_and_label(
            preserve_manual=self.options.preserve_manual
        )
        core.refresh_layer(g, block_data)
        inkex.utils.debug("Block fully auto-labeled using Unified Geometry engine.")

    def _define_section(self):
        """Safely isolates the selection and assigns it an explicit unused letter."""
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")
        tree = block_data.tree

        selected_els = [
            el for el in self.svg.selection.values() if el.get(core.FPP_REGION_ATTR)
        ]
        if not selected_els:
            return inkex.errormsg(
                "Select the pieces you want to group into a section first."
            )

        selected_ids = {int(el.get(core.FPP_REGION_ATTR)) for el in selected_els}

        # 1. Validate that the selection is physically sewable
        is_valid, sequence_ids = tree.virtual_sewing_validator(selected_ids)
        if not is_valid:
            return inkex.errormsg(
                "Invalid Section: The selected pieces cannot be assembled sequentially without a Y-seam."
            )

        # 2. Find an available letter NOT used by the unselected pieces
        used_letters = set()
        for r in tree.leaf_regions():
            if r.id not in selected_ids:
                match = re.match(r"^([A-Za-z]+)", r.label)
                if match:
                    used_letters.add(match.group(1).upper())

        target_letter = "Z"
        for i in range(26):
            char = chr(65 + i)
            if char not in used_letters:
                target_letter = char
                break

        # 3. Apply the clean letter sequence immediately (No rebuild_alphabet needed!)
        # Stamp the group as a MANUAL section so Fully Auto-Label's
        # preserve toggle keeps it together on later reruns.
        tag = 1 + max(
            (r.manual_tag for r in tree.regions.values()
             if r.manual_tag is not None),
            default=0,
        )
        for i, nid in enumerate(sequence_ids):
            region = tree.regions[nid]
            region.label = f"{target_letter}{i + 1}"
            region.manual_tag = tag
            region.manual_first = i == 0

        core.refresh_layer(g, block_data)
        inkex.utils.debug(
            f"Successfully verified and grouped {len(selected_ids)} pieces into Section {target_letter}."
        )

    def _set_first_piece(self):
        """Reordered to safely sequence WITHIN an existing section only."""
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")
        tree = block_data.tree

        selected_els = [
            el for el in self.svg.selection.values() if el.get(core.FPP_REGION_ATTR)
        ]
        if len(selected_els) != 1:
            return inkex.errormsg(
                "Please select EXACTLY ONE piece to set as the start of its section."
            )

        target_id = int(selected_els[0].get(core.FPP_REGION_ATTR))
        target_node = tree.regions[target_id]

        match = re.match(r"^([A-Za-z]+)", target_node.label)
        if not match:
            return inkex.errormsg(
                "Selected piece does not have a standard section letter."
            )
        prefix = match.group(1).upper()

        section_leaves = []
        for r in tree.leaf_regions():
            m = re.match(r"^([A-Za-z]+)", r.label)
            if m and m.group(1).upper() == prefix:
                section_leaves.append(r)
        section_ids = {r.id for r in section_leaves}

        is_valid, sequence_ids = tree.virtual_sewing_validator(
            section_ids, force_start_id=target_id
        )
        if not is_valid:
            return inkex.errormsg(
                "This piece cannot be the first piece without creating a Y-seam."
            )

        for i, nid in enumerate(sequence_ids):
            region = tree.regions[nid]
            region.label = f"{prefix}{i + 1}"
            # Stamp the user's chosen start so auto relabeling keeps it #1
            region.manual_first = nid == target_id

        core.refresh_layer(g, block_data)
        inkex.utils.debug(
            f"Section {prefix} reordered. Selected piece is now {prefix}1."
        )

    def _relabel(self):
        sel = next(
            (el for el in self.svg.selection.values() if el.get(core.FPP_REGION_ATTR)),
            None,
        )
        if sel is None or not self.options.new_label:
            return
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return

        r = block_data.tree.regions.get(int(sel.get(core.FPP_REGION_ATTR)))
        if r:
            r.label = self.options.new_label.strip()
            # Hand-typed labels are never touched by preserve-mode reruns
            r.manual_label = True
            core.refresh_layer(g, block_data)

    def _fix_letters(self):
        g, block_data = core.find_fpp_group(self.svg)
        if g is None:
            return inkex.errormsg("No Quilt Tools FPP block found.")

        tree = block_data.tree
        prefixes = []
        for r in tree.leaf_regions():
            match = re.match(r"^([A-Za-z]+)", r.label)
            if match:
                pref = match.group(1).upper()
                if pref not in prefixes:
                    prefixes.append(pref)

        if not prefixes:
            return inkex.errormsg("No standard section letter labels found to compact.")

        prefixes.sort(key=lambda s: (len(s), s))

        def get_letter_for_index(idx):
            res = []
            temp = idx
            while temp >= 0:
                res.append(chr(65 + (temp % 26)))
                temp = (temp // 26) - 1
            return "".join(reversed(res))

        mapping = {pref: get_letter_for_index(idx) for idx, pref in enumerate(prefixes)}

        changed_count = 0
        for r in tree.leaf_regions():
            match = re.match(r"^([A-Za-z]+)(\d+)$", r.label)
            if match:
                pref, num = match.group(1).upper(), match.group(2)
                if pref in mapping:
                    new_pref = mapping[pref]
                    new_label = f"{new_pref}{num}"
                    if r.label != new_label:
                        r.label = new_label
                        changed_count += 1

        if changed_count > 0:
            core.refresh_layer(g, block_data)
            inkex.utils.debug(
                f"Successfully alphabetized section letters! Remapped {len(prefixes)} sections (changed {changed_count} labels) to be contiguous without gaps."
            )
        else:
            inkex.utils.debug("All section letters are already contiguous and sorted alphabetically. No changes needed.")


if __name__ == "__main__":
    LabelsPlugin().run()
