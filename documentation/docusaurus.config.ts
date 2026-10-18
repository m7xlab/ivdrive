import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'iVDrive',
  tagline: 'Open EV telemetry for Škoda & VW Group',
  favicon: 'img/logo.png',

  future: {
    v4: true,
  },

  url: 'https://ivdrive.eu',
  baseUrl: '/docs/',
  organizationName: 'm7xlab',
  projectName: 'iVDrive',

  onBrokenLinks: 'throw',
  onBrokenMarkdownLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: 'https://github.com/m7xlab/iVDrive/tree/main/documentation/',
          routeBasePath: '/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/docusaurus-social-card.png',
    colorMode: {
      respectPrefersColorScheme: true,
      defaultMode: 'dark',
    },
    navbar: {
      title: 'iVDrive',
      logo: {
        alt: 'iVDrive',
        src: 'img/logo.png',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docsSidebar',
          position: 'left',
          label: 'Documentation',
        },
        {
          to: 'https://ivdrive.eu',
          label: 'Product site',
          position: 'left',
        },
        {
          href: 'https://github.com/m7xlab/iVDrive',
          label: 'GitHub',
          position: 'right',
        },
        {
          href: 'https://ivdrive.eu/register',
          label: 'Request invite',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Learn',
          items: [
            {label: 'Introduction', to: '/docs/intro'},
            {label: 'Quick start', to: '/docs/getting-started/quick-start'},
            {label: 'User guide', to: '/docs/user-guide/dashboard'},
            {label: 'Self-hosting', to: '/docs/self-hosting/overview'},
          ],
        },
        {
          title: 'Community',
          items: [
            {
              label: 'GitHub Discussions',
              href: 'https://github.com/m7xlab/iVDrive/discussions',
            },
            {
              label: 'Issues',
              href: 'https://github.com/m7xlab/iVDrive/issues',
            },
            {
              label: 'Contributing',
              href: 'https://github.com/m7xlab/iVDrive/blob/main/CONTRIBUTING.md',
            },
          ],
        },
        {
          title: 'Product',
          items: [
            {label: 'iVDrive.eu', href: 'https://ivdrive.eu'},
            {label: 'Request invite', href: 'https://ivdrive.eu/register'},
            {label: 'Sign in', href: 'https://ivdrive.eu/login'},
          ],
        },
      ],
      copyright: `© ${new Date().getFullYear()} iVDrive · Elastic License 2.0 (ELv2)`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'yaml', 'json'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
