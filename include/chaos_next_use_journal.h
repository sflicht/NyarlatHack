/* NetHack General Public License. Private, append-only v1 value journal. */
#ifndef CHAOS_NEXT_USE_JOURNAL_H
#define CHAOS_NEXT_USE_JOURNAL_H
#define CHAOS_JOURNAL_LINE_MAX 32768
#define CHAOS_JOURNAL_BYTES_MAX 8388608
#define CHAOS_JOURNAL_RECORDS_MAX 4096
/* Called only after validated runtime_install, before the first transition.
 * Reads the retained runtime snapshot/admission carrier, never a candidate file.
 * Failure affects capture only, not admission or gameplay. */
int chaos_next_use_journal_begin(int dir);
void chaos_next_use_journal_reset(void);
void chaos_next_use_journal_restore_unsupported(void);
#endif
