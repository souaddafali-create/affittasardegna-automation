import http from 'k6/http';
import { sleep, check } from 'k6';

export const options = {
  cloud: {
    name: 'Affittasardegna Load Test',
    environment: 'Default',
  },
  vus: 10,
  duration: '30s',
};

export default function () {
  const res = http.get('https://www.affittasardegna.it/');

  check(res, {
    'status is 200': (r) => r.status === 200,
  });

  sleep(1);
}
