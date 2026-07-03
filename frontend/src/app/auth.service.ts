import { Injectable, signal } from '@angular/core';
import { Observable } from 'rxjs';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { MessageService } from './message.service';
import { LoginData } from './loginData';
import { catchError, tap } from 'rxjs/operators';
import { User } from './user';
import { ServiceBase } from './service-base';
import { environment } from '../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class AuthService extends ServiceBase {
  readonly loggedIn = signal<boolean>(this.isAuthenticated());
  readonly currentUser = signal<User | null>(null);
  redirectUrl: string | null = null;

  private loginURL: string = `${environment.apiBase}/rest-auth/login/`;
  private userURL: string = `${environment.apiBase}/rest-auth/user/`;

  httpOptions = {
    headers: new HttpHeaders({ 'Content-Type': 'application/json' })
  };

  constructor(
    private http: HttpClient,
    protected override messageService: MessageService,
  ) {
    super(messageService);
  }

  login(loginData: any): Observable<LoginData> {
    return this.http.post<LoginData>(this.loginURL, loginData, this.httpOptions)
      .pipe(
        tap((user: LoginData) => {
          this.saveUserToken(user);
          this.loggedIn.set(true);
        }),
        catchError(this.handleError<LoginData>('do login'))
      );
  }

  saveUserToken(user: LoginData): void {
    localStorage.setItem('token', user.key);
  }

  getUserToken(): string | null {
    return localStorage.getItem('token');
  }

  getCurrentUser(): Observable<User> {
    return this.http.get<User>(this.userURL, this.httpOptions)
      .pipe(
        tap((user: User) => this.currentUser.set(user)),
        catchError(this.handleError<User>('get user')));
  }

  public isAuthenticated(): boolean {
    return !!this.getUserToken();
  }
}
