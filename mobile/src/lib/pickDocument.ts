import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';

export type Picked = { base64: string; filename: string };

/** Read a local (file:// or blob:) URI as base64; data: URIs are unpacked directly. */
async function uriToBase64(uri: string): Promise<string> {
  if (uri.startsWith('data:')) return uri.slice(uri.indexOf(',') + 1);
  const blob = await (await fetch(uri)).blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
    reader.onerror = () => reject(new Error("Couldn't read that file."));
    reader.readAsDataURL(blob);
  });
}

// JPEG at 0.7 keeps a phone photo around 0.5-1.5 MB while staying sharp enough for OCR.
const PHOTO: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.7, base64: true, exif: false };

function fromImage(result: ImagePicker.ImagePickerResult): Picked | null {
  if (result.canceled || !result.assets[0]) return null;
  const a = result.assets[0];
  if (!a.base64) throw new Error("Couldn't read that photo.");
  return { base64: a.base64, filename: a.fileName ?? 'photo.jpg' };
}

export async function takePhoto(): Promise<Picked | null> {
  const perm = await ImagePicker.requestCameraPermissionsAsync();
  if (!perm.granted) throw new Error('Allow camera access in Settings to photograph documents.');
  return fromImage(await ImagePicker.launchCameraAsync(PHOTO));
}

export async function choosePhoto(): Promise<Picked | null> {
  return fromImage(await ImagePicker.launchImageLibraryAsync(PHOTO));
}

export async function chooseFile(): Promise<Picked | null> {
  const result = await DocumentPicker.getDocumentAsync({
    type: ['application/pdf', 'image/jpeg', 'image/png'], copyToCacheDirectory: true, multiple: false,
  });
  if (result.canceled || !result.assets[0]) return null;
  const a = result.assets[0];
  if (a.size && a.size > 12 * 1024 * 1024) throw new Error('Files can be up to 12 MB.');
  return { base64: a.base64 ?? (await uriToBase64(a.uri)), filename: a.name };
}
