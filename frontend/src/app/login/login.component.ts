import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { NgClass } from '@angular/common';
import { AuthService } from '../auth.service';
import { ActivatedRoute, Router } from '@angular/router';
import { ReactiveFormsModule, UntypedFormControl, UntypedFormGroup, Validators } from '@angular/forms';
import { catchError } from 'rxjs/operators';
import { throwError } from 'rxjs';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule, NgClass],
  templateUrl: './login.component.html',
  styleUrls: ['./login.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent {
  readonly processing = signal(false);

  form = new UntypedFormGroup({
    email: new UntypedFormControl('', [Validators.required, Validators.email]),
    password: new UntypedFormControl('', Validators.required)
  });

  constructor(
    private authService: AuthService,
    private route: ActivatedRoute,
    private router: Router,
  ) { }

  doLogin(): void {
    this.processing.set(true);
    if (this.form.valid) {
      this.authService.login(this.form.value)
        .pipe(catchError(error => {
          Object.keys(error.error).forEach(field => {
            const formControl = this.form.get(field);
            if (formControl) {
              formControl.setErrors({ serverError: error.error[field] });
            }
          });
          this.form.setErrors({ serverError: error.error['non_field_errors'] });
          this.processing.set(false);
          return throwError(error);
        }))
        .subscribe({
          complete: () => {
            this.processing.set(false);
            this.router.navigate(['tasks']);
          }
        });
    } else {
      this.processing.set(false);
    }
  }
}
