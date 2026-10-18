import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';

import styles from './index.module.css';

const features = [
  {
    title: 'Built for Škoda iV',
    description:
      'Deep telemetry for Enyaq, Elroq and the wider VW Group — trips, charging, battery health in one place.',
  },
  {
    title: 'Self-hostable',
    description:
      'Full Docker Compose stack. Your vehicle credentials stay on your infrastructure.',
  },
  {
    title: 'Driver-grade analytics',
    description:
      'Charging curves, SoH methods, climate and elevation penalties, cost estimates and more.',
  },
];

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <Heading as="h1" className="hero__title">
          iVDrive documentation
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to="/docs/intro">
            Get started
          </Link>
          <Link
            className="button button--outline button--secondary button--lg"
            to="/docs/getting-started/quick-start">
            Quick start
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title="Open EV telemetry for Škoda & VW Group"
      description="Learn how to use and self-host iVDrive — trips, charging, battery health and more.">
      <HomepageHeader />
      <main>
        <section className="container margin-vert--lg">
          <div className="row">
            {features.map((f) => (
              <div key={f.title} className="col col--4 margin-bottom--lg">
                <div className="padding-horiz--md">
                  <Heading as="h3">{f.title}</Heading>
                  <p>{f.description}</p>
                </div>
              </div>
            ))}
          </div>
          <div className="text--center margin-top--lg">
            <Link className="button button--primary button--lg" to="/docs/user-guide/dashboard">
              Open the user guide
            </Link>
          </div>
        </section>
      </main>
    </Layout>
  );
}
