import { Button, Group, Modal, NumberInput, Select, Stack, TextInput } from "@mantine/core";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { MediaFileResponse, MediaFileStatus } from "@/client/types.gen";
import { MEDIA_FILE_STATUSES } from "@/lib/exhaustive-maps";

export interface MediaEditFormValues {
  path: string;
  number: string;
  metadata_id: number | null;
  status: MediaFileStatus;
}

interface MediaEditDialogProps {
  target: MediaFileResponse | null;
  saving: boolean;
  onClose: () => void;
  onSubmit: (values: MediaEditFormValues) => void;
}

export function MediaEditDialog({ target, saving, onClose, onSubmit }: MediaEditDialogProps) {
  const { t } = useTranslation(["library", "common"]);

  return (
    <Modal opened={target != null} onClose={onClose} title={t("editMedia.title")} size="lg">
      {target != null && (
        <MediaEditForm
          key={target.id}
          initialValues={{
            path: target.path,
            number: target.number ?? "",
            metadata_id: target.metadata_id ?? null,
            status: target.status,
          }}
          saving={saving}
          onClose={onClose}
          onSubmit={onSubmit}
        />
      )}
    </Modal>
  );
}

function MediaEditForm({
  initialValues,
  saving,
  onClose,
  onSubmit,
}: {
  initialValues: MediaEditFormValues;
  saving: boolean;
  onClose: () => void;
  onSubmit: (values: MediaEditFormValues) => void;
}) {
  const { t } = useTranslation(["library", "common"]);
  const [path, setPath] = useState(initialValues.path);
  const [number, setNumber] = useState(initialValues.number);
  const [metadataId, setMetadataId] = useState<number | null>(initialValues.metadata_id);
  const [status, setStatus] = useState<MediaFileStatus>(initialValues.status);

  const trimmedPath = path.trim();
  const statusOptions = MEDIA_FILE_STATUSES.map((s) => ({
    value: s,
    label: t(`filters.${s}`),
  }));

  function handleSubmit() {
    if (trimmedPath === "") return;
    onSubmit({
      path: trimmedPath,
      number: number.trim(),
      metadata_id: metadataId,
      status,
    });
  }

  return (
    <Stack>
      <TextInput
        label={t("editMedia.path")}
        description={t("editMedia.pathHint")}
        placeholder={t("editMedia.pathPlaceholder")}
        value={path}
        onChange={(event) => setPath(event.currentTarget.value)}
        error={trimmedPath === "" ? t("editMedia.pathRequired") : undefined}
        required
        data-autofocus
      />
      <TextInput
        label={t("editMedia.number")}
        placeholder={t("editMedia.numberPlaceholder")}
        value={number}
        onChange={(event) => setNumber(event.currentTarget.value)}
      />
      <NumberInput
        label={t("editMedia.metadataId")}
        description={t("editMedia.metadataIdHint")}
        value={metadataId ?? ""}
        min={1}
        allowDecimal={false}
        allowNegative={false}
        onChange={(val) => {
          if (val === "" || val == null) {
            setMetadataId(null);
            return;
          }
          const parsed = typeof val === "number" ? val : Number.parseInt(val, 10);
          setMetadataId(Number.isNaN(parsed) ? null : parsed);
        }}
      />
      <Select
        label={t("editMedia.status")}
        value={status}
        data={statusOptions}
        allowDeselect={false}
        onChange={(val) => {
          if (val) setStatus(val as MediaFileStatus);
        }}
      />
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose} disabled={saving}>
          {t("common:actions.cancel")}
        </Button>
        <Button loading={saving} disabled={trimmedPath === ""} onClick={handleSubmit}>
          {t("editMedia.submit")}
        </Button>
      </Group>
    </Stack>
  );
}
