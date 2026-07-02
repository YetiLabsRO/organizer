import {Observable, of, throwError} from 'rxjs';
import {MessageService} from './message.service';

export class ServiceBase {

  constructor(
    protected messageService: MessageService) {
  }

  protected handleError<T>(operation = 'operation', result?: T) {
    return (error: any): Observable<T> => {
      this.log(`${operation} failed ${error.message}`);
      return throwError(error);
    }
  }

  protected log(message: string) {
    this.messageService.add(`TaskService: ${message}`);
  }
}
