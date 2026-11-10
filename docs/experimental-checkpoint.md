# Experimental checkpoint selection — HIGH RISK

> ⚠️ **EXPERIMENTAL / NO WARRANTY / USE ENTIRELY AT YOUR OWN RISK.**
> This is **not a verified APFS repair product** and is **not a true transactional rollback**.
> It modifies checkpoint superblock headers **on a newly created clone**, causing newer checkpoint candidates to become invalid. This intentionally produces invalid checksums in those newer headers. It does not restore overwritten blocks or repair all container metadata.
> It might render an image unbootable, corrupt other recoverable data after a boot or write, or have unpredictable results on different APFS implementations.

The utility is included because a related checkpoint-selection experiment was instrumental in recovering **one** Catalina VM. It is offered for forensic research and replication on **disposable, independently backed-up copies**. The original recovery used an earlier program to **automatically nominate** a candidate XID after scanning older Data volume superblocks and checking Object Map headers/tree-root types. That was a heuristic, not proof of a safe checkpoint. This public tool currently requires an explicit XID parameter and does not yet incorporate the automatic nomination step.

## Preconditions

- An **offline whole-disk RAW** image with GPT/APFS, **not** a live physical disk or mounted writable VM image.
- A **verified, separate backup** of your complete original image.
- macOS with an **APFS** destination volume supporting `cp -c` copy-on-write cloning.
- Sufficient available storage to accommodate a potentially large clone (and any additional conversion).
- Independent expertise to decide whether the candidate is worth inspecting.
- Do **not** put this into an automated recovery loop or try it on the only copy.

## Step 1: inspect without changes

```bash
python3 experimental/checkpoint_select.py scan --source "/path/to/original.raw"
```

This lists historical checkpoint **candidates** only. It does not validate their complete trees.

## Step 2: create a disposable candidate (modifies clone only)

```bash
python3 experimental/checkpoint_select.py build \
  --source "/path/to/original.raw" \
  --output "/path/to/new-test-candidate.raw" \
  --xid 0xEXAMPLE \
  --i-understand-this-can-destroy-data
```

**Replace `0xEXAMPLE` with an actual XID shown by scan.** The current standalone public script does not automatically nominate the XID; our original recovery workflow did use an automatic heuristic in an earlier step. It refuses to overwrite existing outputs and leaves the original image untouched. Never run `fsck_apfs -y` or other write operations against your original.

## Step 3: independently validate the candidate

1. Review the generated JSON report and inspect the exact changed checkpoint headers.
2. Attach the **clone** read-only and perform an offline `fsck_apfs -n` check.
3. Confirm that the **actual user files you need** are readable from the candidate through a read-only mount.
4. If you test bootability, do so only with a further throwaway VM copy, after safeguarding recovered files, and **never assume a successful first boot means writes or further reboots are safe**.

**Do not use the modified candidate as a production system.** Use it as a temporary way to access recoverable files and move them to a clean, verified filesystem. Expert review of checkpoint dependencies is needed before treating it as repair.

## What this does not do

- It does not determine which historical checkpoint is safe. In the original incident another program automatically nominated a plausible XID, then this checkpoint-selection technique tested it.
- It does not reconstruct a full APFS container transaction, validate its entire Object Map, or ensure System/Data/Preboot coherence.
- It does not guarantee password/login behavior, stable writes, bootability, or complete data recovery.
- It does not substitute for a professional data-recovery service.

[Read the full disclaimer](../DISCLAIMER.md). [Case study](recovery-case.md).

---

# Экспериментальный выбор checkpoint — ВЫСОКИЙ РИСК

Это **не готовый безопасный ремонт APFS**. Скрипт создаёт клон RAW и преднамеренно делает недействительными заголовки более новых контрольных точек только в клоне. Старые транзакции и перезаписанные блоки не восстанавливаются.

Для запуска нужны **отдельная проверенная резервная копия**, невмонтированный исходный RAW, APFS-диск для клонирования, ручной выбор XID и явное подтверждение риска. Всегда сначала `scan`; `build` использовать только для экспериментов с одноразовой копией. После этого проверять `fsck_apfs -n` и реальные пользовательские файлы без записи.

**Всё предоставляется «КАК ЕСТЬ». Пользователь принимает на себя риск полной потери данных.** Для ценных данных предпочтительно обратиться к специалистам.

## Clarification: was the XID chosen manually in the original case?

**No.** A separate *Checkpoint Trial* script automatically found and nominated a candidate older Data volume superblock (XID `0x2b04d`) based on plausible header/tree metadata. The later *Checkpoint Select* step used this previously identified value to create a separate clone and invalidate seven newer checkpoint headers. The user ran tests and confirmed recovered files and macOS boot. That earlier heuristic was not a full APFS consistency validator. The open-source version currently exposes these stages separately; automatic nomination is not yet integrated into the published selector.
