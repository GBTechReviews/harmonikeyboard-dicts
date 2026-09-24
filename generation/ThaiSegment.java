// ThaiSegment.java - Language Batch 10 (2026-09-02). Thai writes no spaces between words, so
// the Tatoeba sentence export cannot be tokenised by gen-tatoeba-words.py's letter runs. This
// tool segments each line with the JDK's DICTIONARY-BASED Thai word BreakIterator (the same
// ICU-derived algorithm Android's java.text.BreakIterator uses at runtime for the keyboard's
// own tail-of-run lookup, ThaiWords.kt) and writes the words back SPACE-SEPARATED, one
// sentence per line, so the ordinary pipeline can count them. Deterministic for a given JDK;
// the provenance record names the JDK that ran it.
//
//   java scripts/ThaiSegment.java tha_text.txt tha_seg.txt
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.BreakIterator;
import java.util.Locale;

public class ThaiSegment {
    public static void main(String[] args) throws IOException {
        BreakIterator bi = BreakIterator.getWordInstance(Locale.forLanguageTag("th-TH"));
        try (BufferedReader in = new BufferedReader(new InputStreamReader(new FileInputStream(args[0]), StandardCharsets.UTF_8));
             Writer out = new OutputStreamWriter(new FileOutputStream(args[1]), StandardCharsets.UTF_8)) {
            String line;
            long lines = 0, words = 0;
            while ((line = in.readLine()) != null) {
                bi.setText(line);
                StringBuilder sb = new StringBuilder(line.length() + 16);
                int start = bi.first();
                for (int end = bi.next(); end != BreakIterator.DONE; start = end, end = bi.next()) {
                    String w = line.substring(start, end).trim();
                    if (w.isEmpty()) continue;
                    if (sb.length() > 0) sb.append(' ');
                    sb.append(w);
                    words++;
                }
                out.write(sb.toString());
                out.write('\n');
                lines++;
            }
            System.out.println("segmented lines=" + lines + " words=" + words + " jdk=" + System.getProperty("java.version"));
        }
    }
}
