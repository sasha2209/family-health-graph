import { File, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

import type { Api } from './api';

/**
 * Save the family as a CanRisk pedigree file and open the share sheet, so the person can send it to their
 * genetic counselor (who loads it into canrisk.org to run BOADICEA). The file has no names in it.
 */
export async function shareCanRiskFile(api: Api): Promise<void> {
  const text = await api.canriskFile();
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'family-canrisk.txt';
    a.click();
    URL.revokeObjectURL(url);
    return;
  }
  const file = new File(Paths.cache, 'family-canrisk.txt');
  if (file.exists) file.delete();
  file.create();
  await file.write(text);
  await Sharing.shareAsync(file.uri, { mimeType: 'text/plain', dialogTitle: 'Send to your genetic counselor' });
}
