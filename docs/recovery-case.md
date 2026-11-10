# Field report: a Catalina APFS recovery

This is an **anonymized account** of one incident, not a general recipe or an endorsement of modifying APFS checkpoint headers. No real names, home directories, private project titles, disk images, user identifiers, authentication data, passwords or original logs are included.

## The failure

A macOS Catalina virtual machine became unbootable. The APFS Data volume's Object Map had an inconsistent link, and a conventional filesystem check did not make the original system usable. The disk image was kept intact; experiments were performed on copies.

## The investigation

- GPT gave the APFS partition offset as **209735680 bytes**. The team initially had to correct a guessed offset.
- Several older container transaction checkpoints (XIDs) survived.
- A one-block Object Map pointer adjustment could make `fsck_apfs` report OK but the guest then showed missing folders, login failures and kernel panics.
- A later attempt using an older existing checkpoint (in this case `0x2b04d`) allowed the Data volume to be read with files present, and all five APFS volumes passed a read-only filesystem check.
- An **experimental checkpoint-selection trial on a separate clone** was followed by a report that the original Catalina environment booted and user files reappeared.
- **Long-term reboot and write stability was not independently established.**

## Why publish this?

No **suitable complete ready-made solution for this particular corruption** was found during the investigation. Online instructions were insufficient for the specific case. Several days went into analyzing metadata and testing candidates, including extensive use of an AI assistant. We publish what can be documented and reproduced so that others can begin with a clearer process rather than repeat the same searches and AI prompts.

This is **not** a factual assertion that no other recovery tools or professional services exist.

## What the tools do — and do not do

The repository includes **read-only** GPT/APFS analysis, RAW block comparison, and a separately documented **experimental clone-only checkpoint selector with automatic candidate nomination**. It is not a validated general-purpose repair tool: modifying APFS metadata without checking the entire transaction can make other disks worse.

**Takeaway:** Validate the GPT-derived partition offset, preserve the original, inspect complete checkpoint dependencies, compare copies, and do not confuse `fsck_apfs` success with actual system bootability or data safety. For irreplaceable data consider a professional lab.
