import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';
import { Platform } from 'react-native';

import type { Api } from './api';

/**
 * Turn the clinician summary into a PDF on the device and open the share
 * sheet (email, Messages, AirDrop, Files, print). Nothing is uploaded anywhere
 * by the app itself. On web, the summary opens in a new tab to print or save.
 */
export async function shareDoctorSummary(api: Api, includeShared = true): Promise<void> {
  const html = await api.clinicianReport(includeShared);
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    globalThis.open?.(url, '_blank', 'noopener');
    return;
  }
  const { uri } = await Print.printToFileAsync({ html, base64: false });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, {
      mimeType: 'application/pdf',
      UTI: 'com.adobe.pdf',
      dialogTitle: 'Share your family health summary',
    });
  } else {
    await Print.printAsync({ uri });
  }
}
