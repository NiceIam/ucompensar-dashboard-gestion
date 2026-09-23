"use client"

import Link from "next/link"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Alert } from "@/components/ui/alert"
import { useAuth } from "@/hooks/use-auth"
import Image from "next/image"

const loginSchema = z.object({
  email: z.string().email("Correo electrónico inválido"),
  password: z.string().min(6, "La contraseña debe tener al menos 6 caracteres"),
})

type LoginFormValues = z.infer<typeof loginSchema>

export default function LoginPage() {
  const { signIn, loading, error } = useAuth()

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: "",
      password: "",
    },
  })

  async function onSubmit(values: LoginFormValues) {
    await signIn(values.email, values.password)
  }

  return (
    <Card className="shadow-lg">
      <CardHeader className="space-y-4 text-center">
        <div className="flex justify-center">
          <Image
            src="/logo-ucompensar.png"
            alt="Compensar Fundación Universitaria"
            width={200}
            height={50}
            className="h-10 w-auto"
            priority
          />
        </div>
        <div>
          <CardTitle className="text-2xl">Bienvenido</CardTitle>
          <CardDescription className="mt-1">
            Plataforma de gestión estratégica de datos con IA
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent>
        {error && (
          <Alert className="mb-4 border-destructive/50 text-destructive">
            {error}
          </Alert>
        )}

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Correo electrónico</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="empresa@ejemplo.com"
                      type="email"
                      autoComplete="email"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Contraseña</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="••••••••"
                      type="password"
                      autoComplete="current-password"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Ingresando..." : "Ingresar"}
            </Button>
          </form>
        </Form>
      </CardContent>

      <CardFooter className="justify-center text-sm text-muted-foreground">
        ¿No tienes cuenta?&nbsp;
        <Link href="/register" className="text-primary hover:underline font-medium">
          Regístrate aquí
        </Link>
      </CardFooter>
    </Card>
  )
}
