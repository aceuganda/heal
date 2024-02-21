import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'heal.aceuganda.org',
  appName: 'heal',
  webDir: '.next',
  server: {
    androidScheme: 'https'
  }
};

export default config;
