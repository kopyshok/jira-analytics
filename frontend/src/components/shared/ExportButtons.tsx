import { Button, Space } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';

interface Props {
  onXlsx?: () => void;
  onPdf?: () => void;
  onPptx?: () => void;
}

export default function ExportButtons({ onXlsx, onPdf, onPptx }: Props) {
  return (
    <Space>
      {onXlsx && <Button icon={<DownloadOutlined />} onClick={onXlsx}>XLSX</Button>}
      {onPdf && <Button icon={<DownloadOutlined />} onClick={onPdf}>PDF</Button>}
      {onPptx && <Button icon={<DownloadOutlined />} onClick={onPptx}>PPTX</Button>}
    </Space>
  );
}
