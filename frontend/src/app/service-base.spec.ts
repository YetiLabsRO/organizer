import { ServiceBase } from './service-base';
import { MessageService } from './message.service';

describe('ServiceBase', () => {
  it('should create an instance', () => {
    expect(new ServiceBase(new MessageService())).toBeTruthy();
  });
});
