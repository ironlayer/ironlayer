{{/*
============================================================================
IronLayer Helm Chart -- Template Helpers
============================================================================
*/}}

{{/*
Expand the name of the chart, truncated to 63 characters (Kubernetes label
length limit) with trailing dashes removed.
*/}}
{{- define "ironlayer.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a fully-qualified app name.  We truncate at 63 characters because some
Kubernetes name fields are limited to this length.  If release name contains
the chart name it will not be duplicated.
*/}}
{{- define "ironlayer.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version for the chart label.
*/}}
{{- define "ironlayer.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
----------------------------------------------------------------------------
Per-component fullname helpers.  Each produces a deterministic, release-
scoped name used for Deployments, Services, ConfigMaps, etc.
----------------------------------------------------------------------------
*/}}

{{- define "ironlayer.api.fullname" -}}
{{- printf "%s-api" (include "ironlayer.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ironlayer.ai.fullname" -}}
{{- printf "%s-ai" (include "ironlayer.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "ironlayer.frontend.fullname" -}}
{{- printf "%s-frontend" (include "ironlayer.fullname" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
----------------------------------------------------------------------------
Common Kubernetes labels following the app.kubernetes.io convention.
These are applied to every resource via `metadata.labels`.
----------------------------------------------------------------------------
*/}}
{{- define "ironlayer.labels" -}}
helm.sh/chart: {{ include "ironlayer.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: ironlayer
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- end }}

{{/*
Per-component labels -- merge the common set with a component identifier.
*/}}
{{- define "ironlayer.api.labels" -}}
{{ include "ironlayer.labels" . }}
app.kubernetes.io/name: {{ include "ironlayer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: api
{{- end }}

{{- define "ironlayer.ai.labels" -}}
{{ include "ironlayer.labels" . }}
app.kubernetes.io/name: {{ include "ironlayer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: ai-engine
{{- end }}

{{- define "ironlayer.frontend.labels" -}}
{{ include "ironlayer.labels" . }}
app.kubernetes.io/name: {{ include "ironlayer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
----------------------------------------------------------------------------
Selector labels -- the minimal set used in `spec.selector.matchLabels` for
Deployments and Services.  Must NOT change between upgrades.
----------------------------------------------------------------------------
*/}}
{{- define "ironlayer.api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ironlayer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: api
{{- end }}

{{- define "ironlayer.ai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ironlayer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: ai-engine
{{- end }}

{{- define "ironlayer.frontend.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ironlayer.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
----------------------------------------------------------------------------
Service account name resolution.  Falls back to the release fullname when
no explicit name is provided.
----------------------------------------------------------------------------
*/}}
{{- define "ironlayer.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "ironlayer.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
----------------------------------------------------------------------------
Image helpers.  Prepend the global registry when configured.
Usage: {{ include "ironlayer.image" (dict "imageRoot" .Values.api.image "global" .Values.global "chart" .Chart) }}
----------------------------------------------------------------------------
*/}}
{{- define "ironlayer.image" -}}
{{- $registry := .global.imageRegistry | default "" -}}
{{- $repository := .imageRoot.repository -}}
{{- $tag := .imageRoot.tag | default .chart.AppVersion -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" $registry $repository $tag -}}
{{- else -}}
{{- printf "%s:%s" $repository $tag -}}
{{- end -}}
{{- end }}

{{/*
Image pull secrets -- merge global list with any per-pod overrides.
*/}}
{{- define "ironlayer.imagePullSecrets" -}}
{{- if .Values.global.imagePullSecrets }}
imagePullSecrets:
{{- range .Values.global.imagePullSecrets }}
  - name: {{ .name }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Secret name helper -- returns the single Opaque secret name.
*/}}
{{- define "ironlayer.secretName" -}}
{{- printf "%s-secrets" (include "ironlayer.fullname" .) }}
{{- end }}
